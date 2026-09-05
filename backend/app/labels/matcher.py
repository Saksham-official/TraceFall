"""Dataset lookup — the `CONFIRMED` half of attribution.

Two sources disagreeing about one address are both returned. Silently picking a winner
would hide exactly the disagreement an investigator needs to see (FR-75), and the one
measured example — an address labelled `MaskEX` by one source and `UEEx` by another
(docs/research/OQ-08-tron-label-coverage.md section 4) — is a conflict between two
different exchanges, not a naming variation.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.blockchain import Address, Chain
from app.db.models.entity import AddressLabel, Entity, LabelSource
from app.db.models.enums import ChainCode, EntityType, LabelReliability


@dataclass(frozen=True, slots=True)
class LabelMatch:
    """One source's claim about one address, with everything needed to cite it."""

    address: str
    entity_id: int | None
    entity_name: str | None
    entity_type: EntityType
    label_text: str
    source_name: str
    source_url: str | None
    dataset_date: date | None
    reliability: LabelReliability

    def as_evidence(self) -> dict[str, object]:
        return {
            "type": "DATASET_MATCH",
            "detail": f"{self.address} appears in {self.source_name} as '{self.label_text}'",
            "source": self.source_name,
            "source_url": self.source_url,
            "dataset_date": self.dataset_date.isoformat() if self.dataset_date else None,
            "reliability": str(self.reliability),
        }


@dataclass(frozen=True, slots=True)
class AddressLabels:
    """Every label held for one address, and whether the sources agree."""

    address: str
    matches: tuple[LabelMatch, ...]

    @property
    def conflicted(self) -> bool:
        """True when sources name different entities. Both are still reported."""
        return len({m.entity_name for m in self.matches if m.entity_name}) > 1

    @property
    def best(self) -> LabelMatch | None:
        """The match to lead with — most reliable source, then most recent dataset.

        Only meaningful when the sources agree; a conflict is presented as a conflict.
        """
        order = {LabelReliability.HIGH: 0, LabelReliability.MEDIUM: 1, LabelReliability.LOW: 2}
        return min(
            self.matches,
            key=lambda m: (order[m.reliability], -(m.dataset_date or date.min).toordinal()),
            default=None,
        )


async def labels_for(
    session: AsyncSession, chain: ChainCode, addresses: list[str]
) -> dict[str, AddressLabels]:
    """Batch lookup. Attribution asks about every address in a trace at once."""
    if not addresses:
        return {}

    result = await session.execute(
        select(
            Address.address,
            Entity.id,
            Entity.name,
            Entity.entity_type,
            AddressLabel.label_text,
            LabelSource.name,
            LabelSource.url,
            LabelSource.dataset_date,
            LabelSource.reliability,
        )
        .select_from(AddressLabel)
        .join(Address, Address.id == AddressLabel.address_id)
        .join(Chain, Chain.id == Address.chain_id)
        .join(LabelSource, LabelSource.id == AddressLabel.label_source_id)
        .outerjoin(Entity, Entity.id == AddressLabel.entity_id)
        .where(Chain.code == chain, Address.address.in_(set(addresses)))
        .order_by(Address.address, LabelSource.name)
    )

    grouped: dict[str, list[LabelMatch]] = {}
    for row in result:
        address = row[0]
        grouped.setdefault(address, []).append(
            LabelMatch(
                address=address,
                entity_id=row[1],
                entity_name=row[2],
                entity_type=row[3] or EntityType.UNKNOWN,
                label_text=row[4],
                source_name=row[5],
                source_url=row[6],
                dataset_date=row[7],
                reliability=row[8],
            )
        )
    return {
        address: AddressLabels(address=address, matches=tuple(matches))
        for address, matches in grouped.items()
    }
