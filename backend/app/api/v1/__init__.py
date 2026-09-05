from fastapi import APIRouter

from app.api.v1 import addresses, analyses, auth, cases, health, reports, results

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(cases.router)
router.include_router(addresses.router)
router.include_router(analyses.router)
router.include_router(results.router)
router.include_router(reports.router)
