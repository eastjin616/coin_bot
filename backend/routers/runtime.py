from fastapi import APIRouter

from backend.runtime_status import get_runtime_status

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


@router.get("/status")
def runtime_status():
    return get_runtime_status()
