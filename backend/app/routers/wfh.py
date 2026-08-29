import logging

from fastapi import APIRouter, HTTPException

from models import WFHRequest
from services.agent_service import run_operation
from logging_utils import safe_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/wfh")
async def work_from_home(payload: WFHRequest):
    logger.info("wfh_request_started session=%s", safe_id(payload.session_id))
    if not payload.start_date.strip() or not payload.end_date.strip():
        raise HTTPException(
            status_code=400,
            detail="Start and end dates are required",
        )

    if not payload.reason.strip():
        raise HTTPException(
            status_code=400,
            detail="Reason is required",
        )

    try:
        result = await run_operation(
            payload.session_id,
            "work_from_home",
            extra={
                "start_date": payload.start_date.strip(),
                "end_date": payload.end_date.strip(),
                "reason": payload.reason.strip(),
                "latitude": payload.location.latitude,
                "longitude": payload.location.longitude,
                "accuracy": payload.location.accuracy,
                "captured_at": payload.location.captured_at,
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    state = result["state"]
    logger.info("wfh_request_finished session=%s status=%s", safe_id(payload.session_id), state.get("status"))

    return {
        "status": state.get("status", "running"),
        "session_id": payload.session_id,
        "operation": "work_from_home",
        "current_step": state.get("current_step"),
        "last_verified_step": state.get("last_verified_step"),
        "details": state.get("result"),
        "message": state.get("action_result"),
        "error": state.get("error"),
        "retry_count": state.get("retry_count", 0),
    }
