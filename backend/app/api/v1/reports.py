"""Report generation and download.

Generation is synchronous. API_SPEC.md describes a 202-and-poll shape for this, which is
the right design when a report takes minutes — this one takes well under a second because
every fact is already in the database and nothing is recomputed. A poll loop for a
sub-second operation is complexity with no user visible on the other end of it; if report
generation ever grows heavy, it moves onto the existing job queue rather than growing a
second one.
"""

import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.deps import SessionDep, get_accessible_case, require_role
from app.core.exceptions import NotFound, StorageUnavailable
from app.db.models.analysis import AnalysisRun
from app.db.models.enums import ReportFormat, ReportType, UserRole
from app.db.models.output import Report
from app.db.models.user import User
from app.reports import assemble, freeze_request, generator
from app.schemas.report import FreezeRequestOut, ReportCreate, ReportOut

router = APIRouter(tags=["reports"])

Investigator = Annotated[
    User, Depends(require_role(UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.ANALYST))
]

MEDIA_TYPES = {
    ReportFormat.PDF: "application/pdf",
    ReportFormat.JSON: "application/json",
    ReportFormat.CSV: "text/csv",
}


def _out(report: Report, verified: bool | None = None) -> ReportOut:
    return ReportOut(
        id=report.id,
        case_id=report.case_id,
        analysis_run_id=report.analysis_run_id,
        report_type=report.report_type,
        format=report.format,
        content_sha256=report.content_sha256,
        narrative_source=report.narrative_source,
        generated_by=report.generated_by,
        generated_at=report.generated_at,
        download_url=f"/api/v1/reports/{report.id}/download",
        content_verified=verified,
    )


@router.post("/cases/{case_id}/reports", response_model=ReportOut, status_code=201)
async def create_report(
    case_id: uuid.UUID, payload: ReportCreate, user: Investigator, session: SessionDep
) -> ReportOut:
    """Generate a report for one analysis run (FR-110..116)."""
    await get_accessible_case(case_id, user, session)

    run = await session.get(AnalysisRun, payload.analysis_run_id)
    if run is None or run.case_id != case_id:
        raise NotFound("Analysis run not found on this case")

    try:
        generated = await generator.generate(
            session,
            run_id=run.id,
            case_id=case_id,
            user_id=user.id,
            report_format=payload.format,
            report_type=payload.report_type,
        )
    except generator.StorageUnavailable as exc:
        raise StorageUnavailable(str(exc)) from exc
    report = await session.get(Report, generated.report_id)
    assert report is not None
    return _out(report, verified=True)


@router.get("/cases/{case_id}/reports", response_model=list[ReportOut])
async def list_reports(
    case_id: uuid.UUID, user: Investigator, session: SessionDep
) -> list[ReportOut]:
    await get_accessible_case(case_id, user, session)
    reports = await session.scalars(
        select(Report).where(Report.case_id == case_id).order_by(Report.generated_at.desc())
    )
    return [_out(report) for report in reports]


@router.get("/reports/{report_id}")
async def get_report(
    report_id: uuid.UUID, user: Investigator, session: SessionDep
) -> dict[str, Any]:
    """Report metadata, including whether the stored file still matches its hash."""
    report = await _accessible_report(report_id, user, session)
    return {
        **_out(report, verified=generator.verify(report)).model_dump(mode="json"),
        # Stated so a reader can check the file themselves rather than trusting this.
        "verification": (
            "SHA-256 of the stored file, recorded when it was written. Re-hash the "
            "downloaded file to confirm it has not changed."
        ),
    }


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: uuid.UUID, user: Investigator, session: SessionDep
) -> FileResponse:
    report = await _accessible_report(report_id, user, session)
    path = Path(report.storage_path)
    if not path.is_file():
        raise NotFound("The stored report file is missing")
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(report.format, "application/octet-stream"),
        filename=f"tracefall-{report.id}.{str(report.format).lower()}",
        headers={"X-Content-SHA256": report.content_sha256},
    )


async def _accessible_report(report_id: uuid.UUID, user: User, session: SessionDep) -> Report:
    report = await session.get(Report, report_id)
    if report is None:
        raise NotFound("Report not found")
    # 404 rather than 403 for a case the user cannot reach, as everywhere else (ADR-013).
    await get_accessible_case(report.case_id, user, session)
    return report


__all__ = ["ReportType", "router"]


@router.get("/analyses/{run_id}/freeze-request", response_model=FreezeRequestOut)
async def get_freeze_request(
    run_id: uuid.UUID, user: Investigator, session: SessionDep
) -> FreezeRequestOut:
    """The letter this analysis supports, as text to review and send.

    Generated on read rather than stored: it is a draft an investigator edits, not a
    record of what was sent, and a stored copy would drift from the analysis behind it.
    """
    run = await session.get(AnalysisRun, run_id)
    if run is None:
        raise NotFound("Analysis run not found")
    await get_accessible_case(run.case_id, user, session)

    data = await assemble.gather(session, run_id)
    to = freeze_request.recipient(data)
    return FreezeRequestOut(
        recipient_name=to["name"],
        recipient_address=to["address"],
        tier=to["tier"],
        confidence=to["confidence"],
        text=freeze_request.render(data),
    )
