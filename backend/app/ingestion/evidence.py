"""Evidence layer (L0).

Raw provider responses, written verbatim and hashed before anything parses them
(FR-22, NFR-10). Bodies live on disk because they are large, append-only, and never
queried by content; the database holds the catalogue.
"""

import gzip
import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.base import RawResponse
from app.core.config import get_settings
from app.db.models.enums import EvidenceType
from app.db.models.output import EvidenceItem

log = logging.getLogger(__name__)


def storage_root() -> Path:
    return Path(get_settings().evidence_storage_path)


def write_body(body: bytes, case_id: uuid.UUID | None) -> tuple[Path, int]:
    """Path is built from a server-generated UUID; user input never reaches it."""
    directory = storage_root() / (str(case_id) if case_id else "unscoped")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}.json.gz"
    compressed = gzip.compress(body)
    path.write_bytes(compressed)
    return path, len(compressed)


async def record(
    session: AsyncSession,
    response: RawResponse,
    case_id: uuid.UUID | None,
    analysis_run_id: uuid.UUID | None = None,
) -> EvidenceItem | None:
    """Persist a response as evidence. Cache hits are not re-recorded.

    Storage failure is logged and swallowed: losing the evidence catalogue entry must not
    fail an investigation that otherwise succeeded. The gap is visible because the
    response's own hash is still reported upstream.
    """
    if response.from_cache:
        return None
    try:
        path, size = write_body(response.body, case_id)
    except OSError:
        log.exception("could not write evidence for %s", response.endpoint)
        return None

    item = EvidenceItem(
        case_id=case_id,
        analysis_run_id=analysis_run_id,
        evidence_type=EvidenceType.API_RESPONSE,
        provider=response.provider,
        endpoint=response.endpoint[:500],
        request_params=response.params,
        http_status=response.status,
        storage_path=str(path),
        content_sha256=response.sha256,
        byte_size=size,
        retrieved_at=response.retrieved_at,
        is_fixture=response.is_fixture,
    )
    session.add(item)
    return item


def read_body(storage_path: str) -> bytes:
    return gzip.decompress(Path(storage_path).read_bytes())
