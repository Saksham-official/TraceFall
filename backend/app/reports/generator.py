"""Producing a report, hashing it, and recording that it exists.

The content hash is taken over **exactly the bytes written to disk**, so a report handed
to a court can be checked against the row that claims to describe it. The bytes are
hashed before they are stored, never after — hashing a file you just read back proves
only that you can read.
"""

import csv
import hashlib
import io
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.enums import NarrativeSource, ReportFormat, ReportType
from app.db.models.output import Report
from app.reports import pdf
from app.reports.assemble import ReportData, gather, headline, risk_headline

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedReport:
    report_id: uuid.UUID
    path: Path
    content_sha256: str
    byte_size: int
    format: ReportFormat
    narrative_source: NarrativeSource


class StorageUnavailable(RuntimeError):
    """The report could not be written. Says where, so it can be fixed."""


def storage_root() -> Path:
    return Path(get_settings().report_storage_path)


def build(data: ReportData, report_id: uuid.UUID, report_format: ReportFormat) -> bytes:
    if report_format is ReportFormat.PDF:
        return pdf.render(data, str(report_id))
    if report_format is ReportFormat.JSON:
        payload = {"report_id": str(report_id), **data.as_dict()}
        return json.dumps(payload, indent=2, default=str).encode()
    return _csv(data)


def _csv(data: ReportData) -> bytes:
    """One row per traced flow, for an investigator who wants it in a spreadsheet."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["from", "to", "tainted_amount_raw", "total_amount_raw", "transfer_count", "tx_hashes"]
    )
    for flow in data.key_transactions:
        writer.writerow(
            [
                flow["from"],
                flow["to"],
                flow["tainted_amount_raw"],
                flow["total_amount_raw"],
                flow["transfer_count"],
                " ".join(str(h) for h in flow["tx_hashes"]),
            ]
        )
    return buffer.getvalue().encode()


async def generate(
    session: AsyncSession,
    run_id: uuid.UUID,
    case_id: uuid.UUID,
    user_id: int,
    report_format: ReportFormat = ReportFormat.PDF,
    report_type: ReportType = ReportType.FULL,
) -> GeneratedReport:
    """Assemble, render, hash, store, record."""
    data = await gather(session, run_id)
    report_id = uuid.uuid4()
    content = build(data, report_id, report_format)
    digest = hashlib.sha256(content).hexdigest()

    directory = storage_root() / str(case_id)
    path = directory / f"{report_id}.{str(report_format).lower()}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except OSError as exc:
        # A 500 with a stack trace tells an operator nothing. Name the setting.
        raise StorageUnavailable(
            f"Could not write the report to {directory}: {exc.strerror}. "
            f"Set REPORT_STORAGE_PATH to a writable directory."
        ) from exc

    session.add(
        Report(
            id=report_id,
            case_id=case_id,
            analysis_run_id=run_id,
            report_type=report_type,
            format=report_format,
            storage_path=str(path),
            content_sha256=digest,
            generated_by=user_id,
            # Templated, always. Nothing writes LLM (ADR-021).
            narrative_source=NarrativeSource.TEMPLATE,
        )
    )
    await session.commit()

    log.info("generated %s report %s for run %s", report_format, report_id, run_id)
    return GeneratedReport(
        report_id=report_id,
        path=path,
        content_sha256=digest,
        byte_size=len(content),
        format=report_format,
        narrative_source=NarrativeSource.TEMPLATE,
    )


def verify(report: Report) -> bool:
    """Re-hash what is on disk and compare. False means the file changed or is gone."""
    path = Path(report.storage_path)
    if not path.is_file():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == report.content_sha256


__all__ = [
    "GeneratedReport",
    "StorageUnavailable",
    "build",
    "generate",
    "headline",
    "risk_headline",
    "storage_root",
    "verify",
]
