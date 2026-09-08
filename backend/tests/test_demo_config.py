"""config/demo_addresses.yaml has to agree with the defaults the intake actually sends.

Nothing in the advanced panel is touched during the demo, so the analysis runs on the
schema defaults while the fixtures were captured for whatever the config says. When those
two drifted apart the demo quietly traced a different window than it was captured for and
one case collapsed to a single node with nothing failing. That is what this file prevents.
"""

from pathlib import Path

import yaml

from app.schemas.analysis import DEFAULT_MAX_DEPTH, DEFAULT_TIME_WINDOW_DAYS

DEMO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "demo_addresses.yaml"


def demo_config() -> dict:
    return yaml.safe_load(DEMO_CONFIG.read_text())


def test_demo_window_matches_the_intake_default() -> None:
    assert demo_config()["window_days"] == DEFAULT_TIME_WINDOW_DAYS


def test_demo_depth_matches_the_intake_default() -> None:
    assert demo_config()["max_depth"] == DEFAULT_MAX_DEPTH


def test_every_demo_address_declares_what_it_should_trace() -> None:
    """Without `expect`, demo_fixtures.py --check cannot tell a shrunk trace from a fine one."""
    for entry in demo_config()["addresses"]:
        expect = entry.get("expect")
        assert expect is not None, f"{entry['address']} has no expect block"
        assert expect.keys() == {"addresses", "edges"}, entry["address"]
