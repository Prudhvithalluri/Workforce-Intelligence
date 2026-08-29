import logging
import re

from fastapi import APIRouter, HTTPException

from models import (
    CheckUsernameRequest,
    LoginRequest,
    OTPRequest,
    RegisterRequest,
)

from services.agent_service import (
    close_session,
    get_session_status,
    resume_with_otp,
    start_login,
)

from services.user_store import (
    find_user,
    register_user,
    verify_app_pin,
)
from logging_utils import safe_id

logger = logging.getLogger(__name__)


router = APIRouter()


# ============================================================
# CHECK USERNAME
# ============================================================

@router.post("/check-username")
async def check_username(
    payload: CheckUsernameRequest,
):
    logger.info("check_username_started user=%s", safe_id(payload.username))
    username = (
        payload.username
        .strip()
        .lower()
    )

    if not username:
        raise HTTPException(
            status_code=400,
            detail="Username is required",
        )

    exists = find_user(username) is not None
    logger.info("check_username_finished user=%s exists=%s", safe_id(username), exists)
    return {
        "exists": exists,
        "username": username,
    }


# ============================================================
# REGISTER
# ============================================================

@router.post("/register")
async def register(
    payload: RegisterRequest,
):
    logger.info("registration_request_started user=%s", safe_id(payload.username))
    try:
        result = register_user(
            payload.username,
            payload.target_password,
            payload.app_pin,
        )

        return {
            "status": "registered",
            **result,
        }

    except ValueError as exc:
        logger.warning("registration_request_rejected user=%s", safe_id(payload.username))
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


# ============================================================
# APPLICATION LOGIN
# ============================================================
#
# IMPORTANT:
#
# This endpoint ONLY:
#
#   1. Checks the user
#   2. Verifies the 4-digit application PIN
#   3. Creates an application session
#   4. Returns the session ID
#   5. Frontend moves to dashboard
#
# It MUST NOT:
#
#   - open Playwright
#   - launch Chromium
#   - open TARGET_SITE_URL
#   - locate target-site username
#   - enter target-site password
#   - call the LLM
#   - ask for target-site OTP
#
# Browser automation starts from /api/attendance/*
# after the user clicks an action on the dashboard.
#
# ============================================================

@router.post("/login")
async def login(
    payload: LoginRequest,
):
    logger.info("login_request_started user=%s", safe_id(payload.username))
    username = (
        payload.username
        .strip()
        .lower()
    )

    if not username:
        raise HTTPException(
            status_code=400,
            detail="Username is required",
        )

    # --------------------------------------------------------
    # USER EXISTS?
    # --------------------------------------------------------

    if not find_user(username):
        logger.warning("login_request_rejected user=%s reason=unknown_user", safe_id(username))
        raise HTTPException(
            status_code=404,
            detail=(
                "User does not exist. "
                "Please register."
            ),
        )

    # --------------------------------------------------------
    # VERIFY APPLICATION PIN
    # --------------------------------------------------------

    if not verify_app_pin(
        username,
        payload.app_pin,
    ):
        logger.warning("login_request_rejected user=%s reason=invalid_pin", safe_id(username))
        raise HTTPException(
            status_code=401,
            detail="Invalid application PIN",
        )

    # --------------------------------------------------------
    # CREATE APPLICATION SESSION ONLY
    # --------------------------------------------------------

    try:
        result = await start_login(
            username
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # start_login() should return:
    #
    #   browser_started = False
    #
    # because the browser must not open until the dashboard
    # action is clicked.
    # --------------------------------------------------------

    return {
        "status": "authenticated",
        "session_id": result["session_id"],
        "username": username,
        "current_step": (
            result["state"].get(
                "current_step"
            )
        ),
        "last_verified_step": (
            result["state"].get(
                "last_verified_step"
            )
        ),
        "browser_started": (
            result.get(
                "browser_started",
                False,
            )
        ),
        "message": (
            "Login successful. "
            "Choose an attendance action."
        ),
    }


# ============================================================
# OTP
# ============================================================
#
# NOTE:
# OTP is part of the target-site automation workflow.
# Therefore it is only valid after an attendance operation
# has started the browser and the graph has interrupted for OTP.
#
# ============================================================

@router.post("/verify-otp")
async def verify_otp(
    payload: OTPRequest,
):
    logger.info("otp_request_started session=%s", safe_id(payload.session_id))

    if not re.fullmatch(r"\d{6}", payload.otp):
        raise HTTPException(
            status_code=400,
            detail="OTP must be a 6-digit number.",
        )

    try:
        result = await resume_with_otp(
            payload.session_id,
            payload.challenge_id,
            payload.otp,
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

    state = result["state"]
    interrupt_payload = result.get(
        "interrupt"
    )

    # --------------------------------------------------------
    # Another user interaction is required.
    # --------------------------------------------------------

    if interrupt_payload:
        return {
            "status": "otp_required",
            "session_id": payload.session_id,
            "otp_required": True,
            "otp_verified": False,
            "otp_invalid": bool(state.get("otp_invalid", False)),
            "challenge_id": (
                interrupt_payload.get("challenge_id")
                or state.get("otp_challenge_id")
            ),
            "current_step": (
                state.get(
                    "current_step"
                )
            ),
            "last_verified_step": (
                state.get(
                    "last_verified_step"
                )
            ),
            "message": (
                interrupt_payload.get(
                    "message"
                )
            ),
        }

    # --------------------------------------------------------
    # OTP accepted and workflow continued.
    #
    # IMPORTANT:
    # The OTP challenge itself succeeded here (otp_verified=True),
    # but the graph does not stop there -- it continues running the
    # SAME operation (login / punch_in / punch_out / work_from_home)
    # to completion inside this call. The "status" reported to the
    # frontend must reflect that real, current workflow status
    # (e.g. "completed", "failed"), not just the OTP outcome, so the
    # dashboard can correctly continue/finish the flow instead of
    # getting stuck showing "OTP verified" forever. "otp_verified" is
    # still returned separately so the frontend can close the OTP
    # modal / show an OTP-specific success message.
    # --------------------------------------------------------

    return {
        "status": state.get("status", "running"),
        "otp_required": bool(state.get("otp_required", False)),
        "otp_verified": bool(state.get("otp_verified", False)),
        "otp_invalid": bool(state.get("otp_invalid", False)),
        "session_id": (
            payload.session_id
        ),
        "operation": state.get("operation"),
        "current_step": (
            state.get(
                "current_step"
            )
        ),
        "last_verified_step": (
            state.get(
                "last_verified_step"
            )
        ),
        "message": (
            state.get("action_result")
            or (
                "OTP verified successfully."
                if state.get("otp_verified")
                else "OTP accepted."
            )
        ),
        "details": state.get(
            "result"
        ),
        "error": state.get(
            "error"
        ),
    }


# ============================================================
# SESSION STATUS
# ============================================================

@router.get(
    "/session/{session_id}"
)
async def session_status(
    session_id: str,
):
    logger.debug("session_status_request session=%s", safe_id(session_id))
    try:
        return get_session_status(
            session_id
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ============================================================
# CANCEL SESSION
# ============================================================

@router.post(
    "/session/{session_id}/cancel"
)
async def cancel_session(
    session_id: str,
):
    logger.info("cancel_request_started session=%s", safe_id(session_id))
    try:
        await close_session(
            session_id
        )

        return {
            "status": "cancelled",
            "session_id": session_id,
        }

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )
