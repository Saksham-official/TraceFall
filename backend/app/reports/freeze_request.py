"""A draft KYC and freeze request, addressed to the service that received the funds.

The PDF answers "where did the money go". This answers "and now what": the last mile
between an analysis and an action is a letter to a VASP, and an investigator writing it by
hand re-types addresses and hashes that are already on screen. A mistyped address sends a
freeze request to nobody.

Three rules shape the text, and all three are about not overclaiming:

**The tier travels into the letter.** A `CONFIRMED` attribution is addressed to the named
exchange. A `PROBABLE` one says, in the letter itself, that the identification is inferred
from transaction behaviour and asks the recipient to confirm it is theirs before acting.
The letter never states as fact what the system holds as an inference (principle 2).

**An unidentified service still gets a letter.** Exchanges do not publish customer deposit
addresses, so most deposit addresses are in no dataset anywhere — but a VASP recognises its
own address immediately. Addressing "the operator of the address below" is the honest form
of that, and it is still actionable, which "we could not identify the exchange" is not.

**It is a draft.** TraceFall is not integrated with NCRP, CFCFRMS or SAHYOG and this letter
is not filed anywhere by us. It is text for an investigator to check, put on their own
letterhead and send under their own authority.
"""

import textwrap
from typing import Any

from app.db.models.enums import AttributionTier, EntityType
from app.reports.assemble import ReportData

# Who a freeze request can sensibly be addressed to. A mixer has no compliance desk and a
# bridge has no customer, so naming either as a recipient would be theatre.
ADDRESSABLE = {str(EntityType.EXCHANGE), str(EntityType.MERCHANT)}

DRAFT_NOTICE = (
    "DRAFT — for review by the investigating officer. TraceFall does not send, file or "
    "transmit this request. Check every value against the analysis before issuing it on "
    "your own letterhead and under your own authority."
)

CAVEAT_PROBABLE = (
    "This identification is INFERRED from transaction behaviour, not confirmed by a "
    "published dataset. It is our assessment, not an established fact. Please confirm "
    "whether the address above is operated by you before acting on this request."
)

CAVEAT_UNIDENTIFIED = (
    "We have not been able to identify the service operating this address from public "
    "data. Exchanges do not publish customer deposit addresses, so this is expected "
    "rather than exceptional. If this address is operated by you, the request below "
    "applies; if it is not, please disregard it."
)


def recipient(data: ReportData) -> dict[str, Any]:
    """Who the letter is addressed to, and on what basis.

    Confirmed service first, then the highest-confidence probable one. Only entity types
    with someone to write to are considered.
    """
    services = [
        a
        for a in data.attributions
        if a["entity_type"] in ADDRESSABLE and a["address"] != data.address["address"]
    ]
    confirmed = [a for a in services if a["tier"] == str(AttributionTier.CONFIRMED)]
    if confirmed:
        best = confirmed[0]
        return {
            "name": best["entity_name"],
            "tier": best["tier"],
            "address": best["address"],
            "confidence": None,
        }

    probable = [
        a for a in services if a["tier"] == str(AttributionTier.PROBABLE) and a["entity_name"]
    ]
    if probable:
        best = max(probable, key=lambda a: a["confidence"] or 0)
        return {
            "name": best["entity_name"],
            "tier": best["tier"],
            "address": best["address"],
            "confidence": best["confidence"],
        }

    # Nothing named. The letter still goes out, addressed to whoever runs the address the
    # money reached — which is the common case, not a failure.
    terminal = _deepest_terminal(data)
    return {
        "name": None,
        "tier": str(AttributionTier.UNATTRIBUTED),
        "address": terminal,
        "confidence": None,
    }


def _deepest_terminal(data: ReportData) -> str | None:
    """The address holding the most traced value where the trace ended."""
    terminals = data.summary.get("terminal_addresses") or []
    for terminal in terminals:
        if terminal.get("address") and terminal["address"] != data.address["address"]:
            return str(terminal["address"])
    return None


def _flows_into(data: ReportData, address: str | None) -> list[dict[str, Any]]:
    if address is None:
        return []
    return [t for t in data.key_transactions if t["to"] == address]


WIDTH = 78


def _wrap(text: str, bullet: str = "") -> list[str]:
    """Long prose at the width the rest of the letter is laid out to.

    A bullet hangs: the marker sits on the first line, the rest indents under it.
    """
    return textwrap.wrap(
        text, width=WIDTH, initial_indent=bullet, subsequent_indent=" " * len(bullet)
    ) or [bullet.rstrip()]


def render(data: ReportData) -> str:
    """The letter, as plain text so it pastes into any word processor or case system."""
    to = recipient(data)
    case = data.case
    suspect = data.address["address"]
    chain = data.address["chain"]
    flows = _flows_into(data, to["address"])

    lines: list[str] = [
        *_wrap(DRAFT_NOTICE),
        "",
        "=" * 78,
        "",
        f"To:      {to['name'] or 'The operator of the address identified below'}",
        f"Subject: Request for KYC records and account restriction — {case['case_number']}",
        "",
        f"Case number:    {case['case_number']}",
    ]
    if case.get("fir_reference"):
        lines.append(f"FIR reference:  {case['fir_reference']}")
    if case.get("ncrp_reference"):
        lines.append(f"NCRP reference: {case['ncrp_reference']}")
    if case.get("incident_date"):
        lines.append(f"Incident date:  {case['incident_date']}")
    lines += [
        f"Issued by:      {case.get('owner') or '[investigating officer]'}",
        f"Generated:      {data.generated_at.isoformat()}",
        "",
        "-" * 78,
        "",
        "Sir/Madam,",
        "",
        "This office is investigating a reported cryptocurrency fraud. Blockchain analysis",
        "of the suspect wallet indicates that value from the reported victim payment reached",
        "an address that appears to be operated by your organisation.",
        "",
        f"Suspect address reported by the victim ({chain}):",
        f"    {suspect}",
    ]

    if data.address.get("reported_amount"):
        symbol = data.address.get("reported_asset_symbol") or ""
        lines += [
            "",
            f"Amount reported by the victim: {data.address['reported_amount']} {symbol}".rstrip(),
        ]
        if data.address.get("reported_at"):
            lines.append(f"Reported time of payment:     {data.address['reported_at']}")

    if to["address"]:
        lines += [
            "",
            "Address believed to be under your control:",
            f"    {to['address']}",
        ]
    if to["tier"] == str(AttributionTier.PROBABLE):
        confidence = to["confidence"] or 0
        lines += [
            "",
            f"Basis: inferred, {confidence * 100:.0f}% confidence.",
            *_wrap(CAVEAT_PROBABLE),
        ]
    elif to["tier"] == str(AttributionTier.CONFIRMED):
        lines += [
            "",
            "Basis: the address appears in a published dataset attributed to your",
            "organisation. It is stated here as an identification, not an inference.",
        ]
    else:
        lines += ["", *_wrap(CAVEAT_UNIDENTIFIED)]

    if flows:
        lines += ["", "Transactions carrying traced value into that address:"]
        for flow in flows:
            lines.append(
                f"    {flow['from']} -> {flow['to']}  "
                f"{flow['transfer_count']} transfer(s), "
                f"{flow['tainted_amount_raw']} raw units traced"
            )
            for tx_hash in flow["tx_hashes"]:
                lines.append(f"        {tx_hash}")
            if flow.get("first_transfer_at"):
                lines.append(
                    f"        between {flow['first_transfer_at']} and {flow['last_transfer_at']}"
                )

    lines += [
        "",
        "We request that you:",
        "",
        "  1. Identify the account associated with the address named above and provide the",
        "     KYC records held for it, including registered name, contact details,",
        "     identity documents and account opening date.",
        "  2. Provide the deposit and withdrawal history for that account covering the",
        "     period of the transactions listed above.",
        "  3. Place a restriction on the account and on any balance traceable to these",
        "     deposits, to the extent your policies and applicable law permit, pending",
        "     further legal process.",
        "  4. Confirm receipt of this request and the action taken.",
        "",
        "Please treat this as urgent. Value held at an exchange is recoverable only while",
        "it remains in the account.",
        "",
        "-" * 78,
        "",
        "Basis and limitations of this request:",
        "",
    ]
    for disclaimer in [*data.disclaimers, data.tracing_convention]:
        lines += _wrap(disclaimer, bullet="  - ")
    lines += [
        "",
        "The full analysis, including every transaction hash behind the flows above and",
        "the reason the trace ended where it did, is available in the accompanying report.",
        "",
        "Yours faithfully,",
        "",
        f"{case.get('owner') or '[investigating officer]'}",
        "",
    ]
    return "\n".join(lines)
