from pathlib import Path

import pytest

from app import worker


def test_heartbeat_is_alive_after_beat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "beat")
    worker.beat()
    assert worker.is_alive()


def test_missing_heartbeat_is_not_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "absent")
    assert not worker.is_alive()


def test_stale_heartbeat_is_not_alive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    beat = tmp_path / "beat"
    beat.write_text("0")  # epoch 0 — long stale
    monkeypatch.setattr(worker, "HEARTBEAT", beat)
    assert not worker.is_alive()
