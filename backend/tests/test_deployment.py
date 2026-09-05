"""Deployment configuration — the parts checkable without a Docker daemon.

Every one of these guards a bug that was actually present: the image was built from a
context that could not see `config/` or `data/`, the runtime data files were located by
counting `..` from `__file__` (which resolves to `/` once the package is installed
elsewhere), and the directories the process writes to were never created for the non-root
user. None of it fails on a developer laptop, and all of it fails in the container.

**These do not replace running the stack.** They check that the configuration is
self-consistent; whether five containers come up healthy is a question only a daemon can
answer, and `docs/DEPLOYMENT.md` says so.
"""

import re
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings, get_settings
from app.core.paths import resolve, resolve_writable
from app.risk import config as risk_config

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
BACKEND_DOCKERFILE = (ROOT / "backend" / "Dockerfile").read_text()


def copied(dockerfile: str) -> list[str]:
    return [
        match.group(1)
        for line in dockerfile.splitlines()
        if (match := re.match(r"COPY (?!--from=)(\S+) ", line.strip()))
    ]


# --- Path resolution ------------------------------------------------------------------


def test_runtime_data_files_are_found_from_any_working_directory(tmp_path: Path) -> None:
    """The bug: `parents[3]` resolved to `/config/risk_weights.yaml` inside the image."""
    import os

    original = Path.cwd()
    try:
        os.chdir(tmp_path)
        found = resolve("config/risk_weights.yaml", setting="RISK_CONFIG_PATH")
        assert found.is_file()
        assert found.read_text().startswith("#")
    finally:
        os.chdir(original)


def test_a_missing_data_file_names_the_setting_that_points_at_it() -> None:
    """ "No such file: /config/risk_weights.yaml" tells an operator nothing."""
    with pytest.raises(FileNotFoundError, match="RISK_CONFIG_PATH"):
        resolve("config/does-not-exist.yaml", setting="RISK_CONFIG_PATH")


def test_an_absolute_path_is_taken_as_given(tmp_path: Path) -> None:
    target = tmp_path / "weights.yaml"
    target.write_text("version: x")

    assert resolve(str(target), setting="RISK_CONFIG_PATH") == target
    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve(str(tmp_path / "absent.yaml"), setting="RISK_CONFIG_PATH")


def test_the_risk_config_loads_through_its_setting() -> None:
    loaded = risk_config.load()

    assert loaded.version
    assert risk_config.default_path().is_file()


def test_a_writable_path_need_not_exist_yet(tmp_path: Path) -> None:
    """Evidence and report directories are made on first use, not required up front."""
    assert resolve_writable(str(tmp_path / "reports")) == tmp_path / "reports"


def test_the_data_path_defaults_are_relative_so_a_container_can_find_them() -> None:
    defaults = Settings(secret_key="x" * 40)  # type: ignore[call-arg]

    for value in (
        defaults.risk_config_path,
        defaults.label_data_path,
        defaults.fixture_path,
    ):
        assert not value.startswith("/"), value


# --- The image ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "why"),
    [
        ("backend/alembic", "`alembic upgrade head` is the first documented command"),
        ("backend/alembic.ini", "alembic needs its config"),
        ("config", "the RISK stage reads config/risk_weights.yaml on every analysis"),
        ("data", "load-labels, and therefore every CONFIRMED attribution"),
        ("backend/tests/fixtures", "LIVE_MODE=false is the default and the demo path"),
    ],
)
def test_the_image_carries_what_the_application_reads(path: str, why: str) -> None:
    """Each of these was missing, and each failed a different documented step."""
    assert path in copied(BACKEND_DOCKERFILE), f"{path} is not COPYed: {why}"


def test_every_copy_source_exists_in_the_build_context() -> None:
    """A COPY of a path that is not there fails the build, not the test suite."""
    missing = [source for source in copied(BACKEND_DOCKERFILE) if not (ROOT / source).exists()]

    assert missing == []


def test_the_image_runs_as_a_non_root_user() -> None:
    assert "USER tracefall" in BACKEND_DOCKERFILE
    # And owns what it writes to: a volume mounted over a path the image did not create
    # arrives root-owned and the first report fails.
    assert "/data/reports" in BACKEND_DOCKERFILE
    assert "/data/evidence" in BACKEND_DOCKERFILE
    assert "chown" in BACKEND_DOCKERFILE


def test_the_image_is_multi_stage_so_build_tools_do_not_ship() -> None:
    assert BACKEND_DOCKERFILE.count("FROM ") >= 2
    assert "--from=build" in BACKEND_DOCKERFILE


def test_no_secret_is_baked_into_the_image() -> None:
    """Credentials arrive as environment at run time, never in a layer."""
    for forbidden in ("SECRET_KEY=", "POSTGRES_PASSWORD=", "API_KEY="):
        assert forbidden not in BACKEND_DOCKERFILE
    assert "COPY .env " not in BACKEND_DOCKERFILE
    ignored = (ROOT / ".dockerignore").read_text()
    assert ".env" in ignored


# --- Compose --------------------------------------------------------------------------


def test_only_the_web_service_is_exposed() -> None:
    """Postgres, Redis, the API and the worker are reachable only inside the network."""
    exposed = {name: service.get("ports") for name, service in COMPOSE["services"].items()}

    assert [name for name, ports in exposed.items() if ports] == ["web"]


def test_every_service_has_a_healthcheck() -> None:
    for name, service in COMPOSE["services"].items():
        assert "healthcheck" in service, f"{name} has no healthcheck"


def test_the_api_and_worker_wait_for_their_dependencies() -> None:
    for name in ("api", "worker"):
        depends = COMPOSE["services"][name]["depends_on"]
        assert depends["postgres"]["condition"] == "service_healthy"
        assert depends["redis"]["condition"] == "service_healthy"


def test_state_is_on_named_volumes_so_it_survives_a_restart() -> None:
    assert set(COMPOSE["volumes"]) == {
        "postgres_data",
        "redis_data",
        "evidence_data",
        "report_data",
    }
    for name in ("api", "worker"):
        mounts = COMPOSE["services"][name]["volumes"]
        assert "evidence_data:/data/evidence" in mounts
        assert "report_data:/data/reports" in mounts


def test_the_backend_image_is_built_from_the_repository_root() -> None:
    """It needs config/ and data/, which live above backend/."""
    for name in ("api", "worker"):
        build = COMPOSE["services"][name]["build"]
        assert build["context"] == "."
        assert build["dockerfile"] == "backend/Dockerfile"


def test_the_env_example_documents_every_setting_compose_requires() -> None:
    example = (ROOT / ".env.example").read_text()
    required = set(re.findall(r"\$\{(\w+)\}", (ROOT / "docker-compose.yml").read_text()))

    missing = [name for name in required if f"{name}=" not in example]
    assert missing == [], f".env.example is missing {missing}"


def test_the_settings_the_container_overrides_are_all_documented() -> None:
    example = (ROOT / ".env.example").read_text()

    for name in ("EVIDENCE_STORAGE_PATH", "REPORT_STORAGE_PATH", "RISK_CONFIG_PATH"):
        assert f"{name}=" in example, f"{name} is not in .env.example"
    assert get_settings().environment in ("development", "production")
