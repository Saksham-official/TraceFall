import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

# Force LIVE_MODE=false so retrieval reads committed fixtures
os.environ["LIVE_MODE"] = "false"
os.environ.setdefault("SECRET_KEY", "dev-secret-key-for-local-development-32chars")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://tracefall:tracefall@localhost:5432/tracefall")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from sqlalchemy import select
from app.db.session import SessionFactory
from app.db.models.user import User
from app.db.models.case import Case, CaseAddress
from app.db.models.blockchain import Address, Chain
from app.db.models.analysis import AnalysisRun
from app.db.models.enums import CaseStatus, Priority, AddressRole, ChainCode, AnalysisStatus
from app.worker import _run_pipeline
from app.reports.generator import generate as generate_report, ReportFormat, ReportType

ADMIN_EMAIL = os.environ.get("DEMO_ADMIN_EMAIL", "admin@example.gov")

COMPLEX_CASE_TITLE = "Complex Fund Movement"
COMPLEX_ADDRESS = "T9yD14Nj9j7xAB4dbGeiX9h8uo1syi2Ves"

BINANCE_CASE_TITLE = "Binance Fraud Trail"
BINANCE_ADDRESS = "T9yD14Nj9j7xAB4dbGeiX9h8unyw8chUDN"


async def seed():
    async with SessionFactory() as session:
        # 1. Ensure admin user exists
        admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if not admin:
            raise RuntimeError(
                f"No admin {ADMIN_EMAIL} exists. Run 'python -m app.cli create-admin' first."
            )

        # Ensure TRON chain row exists
        tron_chain = await session.scalar(select(Chain).where(Chain.code == ChainCode.TRON))
        if not tron_chain:
            raise RuntimeError("TRON chain reference data not found in DB")

        # 2. Seed "Complex Fund Movement" case
        complex_case = await session.scalar(select(Case).where(Case.title == COMPLEX_CASE_TITLE))
        if not complex_case:
            complex_case = Case(
                case_number="TF-2026-0001",
                title=COMPLEX_CASE_TITLE,
                ncrp_reference="NCRP-2026-884920",
                fir_reference="FIR-2026/0492",
                description=(
                    "Multi-hop laundering scheme featuring fund splitting, peel-chain layering "
                    "across hub and branch wallets, fan-in consolidation, and automated VASP deposit address sweep."
                ),
                reported_loss_inr=1500000.00,
                priority=Priority.HIGH,
                status=CaseStatus.OPEN,
                owner_id=admin.id,
            )
            session.add(complex_case)
            await session.commit()
            await session.refresh(complex_case)
            print(f"Created case: {complex_case.title} ({complex_case.case_number})")

        # Ensure Address row for COMPLEX_ADDRESS
        complex_addr_row = await session.scalar(
            select(Address).where(Address.chain_id == tron_chain.id, Address.address == COMPLEX_ADDRESS)
        )
        if not complex_addr_row:
            complex_addr_row = Address(chain_id=tron_chain.id, address=COMPLEX_ADDRESS)
            session.add(complex_addr_row)
            await session.commit()
            await session.refresh(complex_addr_row)

        # Ensure CaseAddress row
        complex_case_addr = await session.scalar(
            select(CaseAddress).where(
                CaseAddress.case_id == complex_case.id,
                CaseAddress.address_id == complex_addr_row.id,
            )
        )
        if not complex_case_addr:
            complex_case_addr = CaseAddress(
                case_id=complex_case.id,
                address_id=complex_addr_row.id,
                role=AddressRole.SUSPECT,
                reported_amount=50000,
                reported_asset_symbol="USDT",
                added_by=admin.id,
            )
            session.add(complex_case_addr)
            await session.commit()
            await session.refresh(complex_case_addr)

        # 3. Check for completed AnalysisRun for Complex Fund Movement
        complex_run = await session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.case_id == complex_case.id,
                AnalysisRun.root_address_id == complex_addr_row.id,
                AnalysisRun.status.in_([AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL]),
            )
        )

        if not complex_run:
            print("Running analysis pipeline for Complex Fund Movement...")
            run = AnalysisRun(
                case_id=complex_case.id,
                root_address_id=complex_addr_row.id,
                params={"time_window_days": 180, "max_depth": 5, "asset_symbol": "USDT"},
                status=AnalysisStatus.QUEUED,
                triggered_by=admin.id,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            # Execute pipeline
            await _run_pipeline(run.id)
            await session.refresh(run)
            print(f"Analysis completed with status: {run.status}")

            # Generate PDF/JSON report
            try:
                async with SessionFactory() as r_session:
                    await generate_report(r_session, run.id, complex_case.id, admin.id, ReportFormat.PDF, ReportType.FULL)
                    print("Generated PDF report for Complex Fund Movement")
            except Exception as e:
                print(f"Report generation note: {e}")
        else:
            print(f"Analysis for Complex Fund Movement already exists (status: {complex_run.status})")

        # 4. Seed "Binance Fraud Trail" case for live demo
        binance_case = await session.scalar(select(Case).where(Case.title == BINANCE_CASE_TITLE))
        if not binance_case:
            binance_case = Case(
                case_number="TF-2026-0002",
                title=BINANCE_CASE_TITLE,
                ncrp_reference="NCRP-2026-773104",
                fir_reference="FIR-2026/0311",
                description=(
                    "Victim-reported fraud wallet receiving 100,000 USDT. Funds split across intermediary wallets, "
                    "consolidated into a deposit address, and swept directly into a confirmed Binance collection wallet."
                ),
                reported_loss_inr=8300000.00,
                priority=Priority.CRITICAL,
                status=CaseStatus.OPEN,
                owner_id=admin.id,
            )
            session.add(binance_case)
            await session.commit()
            await session.refresh(binance_case)
            print(f"Created case: {binance_case.title} ({binance_case.case_number})")

        binance_addr_row = await session.scalar(
            select(Address).where(Address.chain_id == tron_chain.id, Address.address == BINANCE_ADDRESS)
        )
        if not binance_addr_row:
            binance_addr_row = Address(chain_id=tron_chain.id, address=BINANCE_ADDRESS)
            session.add(binance_addr_row)
            await session.commit()
            await session.refresh(binance_addr_row)

        binance_case_addr = await session.scalar(
            select(CaseAddress).where(
                CaseAddress.case_id == binance_case.id,
                CaseAddress.address_id == binance_addr_row.id,
            )
        )
        if not binance_case_addr:
            binance_case_addr = CaseAddress(
                case_id=binance_case.id,
                address_id=binance_addr_row.id,
                role=AddressRole.SUSPECT,
                reported_amount=100000,
                reported_asset_symbol="USDT",
                added_by=admin.id,
            )
            session.add(binance_case_addr)
            await session.commit()
            print(f"Attached address {BINANCE_ADDRESS} to Binance Fraud Trail")

    print("\n--- SEED COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(seed())
