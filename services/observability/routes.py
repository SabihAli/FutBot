from fastapi import APIRouter, HTTPException

from futbot_common.responses import DataResponse
from services.observability.trace_store import get_run_trace

router = APIRouter(tags=["traces"])


@router.get("/traces/{run_id}", response_model=DataResponse[dict])
def get_trace(run_id: int) -> DataResponse[dict]:
    trace = get_run_trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return DataResponse(data=trace)
