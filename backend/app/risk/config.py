"""Loading the versioned weight catalogue.

Weights live in `config/risk_weights.yaml`, not in code (FR-85), and the version is
recorded in every assessment (FR-86) so a score generated months ago stays explicable
after the numbers change.

The file is validated on load rather than trusted: a typo in a weight would silently
change every score in the system, and a score nobody can reproduce is worse than no
score.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings
from app.core.paths import resolve
from app.db.models.enums import RiskBand

ENGINE_VERSION = "1.0.0"


class SignalConfig(BaseModel):
    """One signal's tuning. Extra keys are the per-signal scaling parameters."""

    weight: float = Field(ge=0, le=100)
    # A — direct risk contact · B — laundering behaviour · C — address characteristics
    # · D — case context. Load-bearing: B and C describe behaviour a confirmed service
    # exhibits by design, and are not evaluated for one.
    group: Literal["A", "B", "C", "D"]
    enabled: bool = True

    model_config = {"extra": "allow"}

    def get(self, key: str, default: float) -> float:
        value = (self.__pydantic_extra__ or {}).get(key, default)
        return float(value)


class ConfidenceWeights(BaseModel):
    data_completeness: float = Field(ge=0, le=1)
    attribution_quality: float = Field(ge=0, le=1)
    trace_completeness: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "ConfidenceWeights":
        total = self.data_completeness + self.attribution_quality + self.trace_completeness
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"confidence weights must sum to 1.0, got {total}")
        return self


class RiskConfig(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    bands: dict[RiskBand, tuple[int, int]]
    confidence: ConfidenceWeights
    signals: dict[str, SignalConfig]

    @model_validator(mode="after")
    def _bands_cover_the_range(self) -> "RiskConfig":
        """Every score from 0 to 100 must land in exactly one band, with no gaps."""
        ordered = sorted(self.bands.items(), key=lambda item: item[1][0])
        if ordered[0][1][0] != 0 or ordered[-1][1][1] != 100:
            raise ValueError("bands must cover 0 to 100")
        for (_, (_, upper)), (_, (lower, _)) in zip(ordered, ordered[1:], strict=False):
            if lower != upper + 1:
                raise ValueError(f"bands leave a gap or overlap between {upper} and {lower}")
        return self

    def signal(self, name: str) -> SignalConfig | None:
        found = self.signals.get(name)
        return found if found is not None and found.enabled else None

    def band_for(self, score: int) -> RiskBand:
        for band, (lower, upper) in self.bands.items():
            if lower <= score <= upper:
                return band
        raise ValueError(f"score {score} falls outside every band")


def default_path() -> Path:
    return resolve(get_settings().risk_config_path, setting="RISK_CONFIG_PATH")


def load(path: Path | None = None) -> RiskConfig:
    raw: dict[str, Any] = yaml.safe_load((path or default_path()).read_text())
    return RiskConfig.model_validate(raw)


@lru_cache(maxsize=1)
def active() -> RiskConfig:
    """The running configuration. Cached because it is read once per scored address."""
    return load()
