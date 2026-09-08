"""The draft KYC and freeze request.

This is the artefact that leaves the building and lands on an exchange's compliance desk,
so the tests are about what it claims rather than how it reads. A PROBABLE attribution
must never be worded as an identification; an unidentified service must still produce an
actionable letter rather than an apology; and the recipient must never be a mixer, which
has no compliance desk to receive it.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import AttributionTier, EntityType
from app.db.models.user import User
from app.reports import freeze_request
from app.reports.assemble import ReportData
from tests.conftest import auth, login, make_user
from tests.test_reports import analysed, storage  # noqa: F401  (storage is an autouse fixture)


def flat(text: str) -> str:
    """The letter with its line breaks collapsed.

    The prose is wrapped to 78 columns for print, so asserting on a sentence has to be
    about what it says rather than where it happened to break.
    """
    return " ".join(text.split())


SUSPECT = "TUcjuVB6RFvsMgE352Kdc3VHvFvteti97B"
DEPOSIT = "TWBAPzpPiZarfVsY2BLXeaLhNHurn4wkWG"
MIXER = "TLFqEhiG7RUSZ9x5iph99Ke5782dkgRnWf"


def report(attributions: list[dict], terminal: str = DEPOSIT) -> ReportData:
    return ReportData(
        case={
            "case_number": "TF-2026-0001",
            "title": "Victim one",
            "fir_reference": "FIR/2026/17",
            "ncrp_reference": None,
            "incident_date": "2026-08-01",
            "owner": "Inspector R. Sharma",
        },
        address={
            "address": SUSPECT,
            "chain": "TRON",
            "reported_amount": "50000",
            "reported_asset_symbol": "USDT",
            "reported_at": "2026-08-01T09:00:00+00:00",
        },
        run={},
        summary={"terminal_addresses": [{"address": terminal, "reason": "SERVICE_BOUNDARY"}]},
        key_transactions=[
            {
                "from": SUSPECT,
                "to": DEPOSIT,
                "tainted_amount_raw": "50000000000",
                "transfer_count": 2,
                "tx_hashes": ["a" * 64, "b" * 64],
                "first_transfer_at": "2026-08-01T09:05:00+00:00",
                "last_transfer_at": "2026-08-01T09:40:00+00:00",
            }
        ],
        attributions=attributions,
        generated_at=datetime(2026, 9, 9, tzinfo=UTC),
    )


def attribution(tier: AttributionTier, entity_type: EntityType, **over: object) -> dict:
    return {
        "address": DEPOSIT,
        "tier": str(tier),
        "entity_name": "Binance",
        "entity_type": str(entity_type),
        "confidence": None,
        "method": "DATASET_MATCH",
        "evidence": [],
        **over,
    }


def test_a_confirmed_exchange_is_addressed_by_name() -> None:
    text = freeze_request.render(
        report([attribution(AttributionTier.CONFIRMED, EntityType.EXCHANGE)])
    )

    assert "To:      Binance" in text
    assert "stated here as an identification, not an inference" in flat(text)
    assert flat(freeze_request.CAVEAT_PROBABLE) not in flat(text)


def test_a_probable_attribution_is_never_worded_as_an_identification() -> None:
    """The integrity rule that matters most here: the tier travels into the letter."""
    text = freeze_request.render(
        report(
            [
                attribution(
                    AttributionTier.PROBABLE,
                    EntityType.EXCHANGE,
                    confidence=0.82,
                    method="DEPOSIT_HEURISTIC",
                )
            ]
        )
    )

    assert flat(freeze_request.CAVEAT_PROBABLE) in flat(text)
    assert "INFERRED from transaction behaviour" in flat(text)
    assert "82% confidence" in text
    assert "not an inference" not in flat(text)


def test_an_unidentified_service_still_gets_an_actionable_letter() -> None:
    """Most deposit addresses are in no dataset. That is not a reason to send nothing."""
    text = freeze_request.render(report([]))

    assert "The operator of the address identified below" in text
    assert flat(freeze_request.CAVEAT_UNIDENTIFIED) in flat(text)
    # The address and the hashes are what make it actionable at all.
    assert DEPOSIT in text
    assert "a" * 64 in text


def test_a_mixer_is_never_addressed_as_a_recipient() -> None:
    """A mixer has no compliance desk. Naming one as the recipient would be theatre."""
    to = freeze_request.recipient(
        report([attribution(AttributionTier.CONFIRMED, EntityType.MIXER, address=MIXER)])
    )

    assert to["name"] is None
    assert to["tier"] == str(AttributionTier.UNATTRIBUTED)


def test_the_letter_says_it_is_a_draft_and_claims_no_filing() -> None:
    text = freeze_request.render(report([]))

    assert flat(text).startswith(flat(freeze_request.DRAFT_NOTICE))
    assert "TraceFall does not send, file or transmit this request" in flat(text)
    # The claims checklist words appear only as denials, never as claims.
    assert "is not a forensic certification and is not court-admissible" in flat(text)
    assert "cannot identify the person behind an address" in flat(text)


def test_the_case_and_victim_facts_come_from_the_case_not_the_letter() -> None:
    text = freeze_request.render(report([]))

    assert "TF-2026-0001" in text
    assert "FIR/2026/17" in text
    assert "50000 USDT" in text
    assert "Inspector R. Sharma" in text


# --- Through the API ------------------------------------------------------------------


@pytest.mark.usefixtures("storage")
async def test_the_endpoint_returns_the_letter_and_its_tier(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, _, user_id = await analysed(session)
    owner = await session.get(User, user_id)
    assert owner is not None
    token = await login(client, owner.email)

    response = await client.get(f"/api/v1/analyses/{run_id}/freeze-request", headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["tier"] in {t.value for t in AttributionTier}
    assert flat(freeze_request.DRAFT_NOTICE) in flat(body["text"])
    assert "Request for KYC records and account restriction" in flat(body["text"])


@pytest.mark.usefixtures("storage")
async def test_another_investigator_cannot_read_the_letter(
    client: AsyncClient, session: AsyncSession
) -> None:
    run_id, _, _ = await analysed(session)
    await make_user(session, "outsider@example.gov")
    token = await login(client, "outsider@example.gov")

    response = await client.get(f"/api/v1/analyses/{run_id}/freeze-request", headers=auth(token))

    assert response.status_code == 404, "403 would confirm the analysis exists"
