import logging

from fastapi import APIRouter, HTTPException

from models import OperationRequest
from services.agent_service import run_operation
from logging_utils import safe_id

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# COMMON ATTENDANCE RUNNER
# ============================================================

async def _run(
    payload: OperationRequest,
    operation: str,
):
    logger.info("attendance_request_started operation=%s session=%s", operation, safe_id(payload.session_id))
    """
    Start an attendance workflow.

    IMPORTANT:
    This endpoint is called only after the user clicks an
    attendance action on the dashboard.

    The frontend supplies the current location. The backend
    then starts Playwright and the LangGraph/LLM workflow.
    """

    if operation not in {
        "punch_in",
        "punch_out",
        "work_from_home",
    }:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported operation: {operation}",
        )

    try:
        result = await run_operation(
            payload.session_id,
            operation,
            extra={
                "latitude": payload.location.latitude,
                "longitude": payload.location.longitude,
                "accuracy": payload.location.accuracy,
                "captured_at": payload.location.captured_at,
            },
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    state = result.get(
        "state",
        {},
    )
    logger.info("attendance_request_finished operation=%s session=%s status=%s", operation, safe_id(payload.session_id), state.get("status"))

    interrupt_payload = result.get(
        "interrupt"
    )

    # --------------------------------------------------------
    # OTP / USER INTERACTION REQUIRED
    # --------------------------------------------------------

    if interrupt_payload:

        return {
            "status": "waiting",
            "session_id": payload.session_id,
            "operation": operation,

            "current_step": state.get(
                "current_step"
            ),

            "last_verified_step": state.get(
                "last_verified_step"
            ),

            "message": (
                interrupt_payload.get(
                    "message",
                    "User input required.",
                )
            ),

            "challenge_id": (
                interrupt_payload.get("challenge_id")
                or state.get("otp_challenge_id")
            ),
            "otp_required": bool(state.get("otp_required", True)),
            "otp_verified": bool(state.get("otp_verified", False)),
            "otp_invalid": bool(state.get("otp_invalid", False)),

            "browser_started": result.get(
                "browser_started",
                True,
            ),
        }

    # --------------------------------------------------------
    # NORMAL RESULT
    # --------------------------------------------------------

    return {
        "status": state.get(
            "status",
            "running",
        ),

        "session_id": payload.session_id,

        "operation": operation,

        "current_step": state.get(
            "current_step"
        ),

        "last_verified_step": state.get(
            "last_verified_step"
        ),

        "details": state.get(
            "result"
        ),

        "message": (
            state.get(
                "action_result"
            )
            or state.get(
                "message"
            )
        ),

        "error": state.get(
            "error"
        ),

        "retry_count": state.get(
            "retry_count",
            0,
        ),
        "otp_required": bool(state.get("otp_required", False)),
        "otp_verified": bool(state.get("otp_verified", False)),
        "otp_invalid": bool(state.get("otp_invalid", False)),

        "browser_started": result.get(
            "browser_started",
            True,
        ),
    }


# ============================================================
# PUNCH IN
# ============================================================

@router.post("/punch-in")
async def punch_in(
    payload: OperationRequest,
):
    """
    Punch In.

    Browser automation starts only when this endpoint is
    called by the dashboard.
    """

    return await _run(
        payload,
        "punch_in",
    )


# ============================================================
# PUNCH OUT
# ============================================================

@router.post("/punch-out")
async def punch_out(
    payload: OperationRequest,
):
    """
    Punch Out.

    Browser automation starts only when this endpoint is
    called by the dashboard.
    """

    return await _run(
        payload,
        "punch_out",
    )


