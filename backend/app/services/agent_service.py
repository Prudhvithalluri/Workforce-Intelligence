
import logging

from langgraph.types import Command

from agent.graph import graph
from browser.session import session_manager
from services.user_store import find_user, get_target_password
from logging_utils import safe_id
from datetime import datetime,timezone
logger = logging.getLogger(__name__)


def config_for(session_id: str):
    logger.debug("graph_config_created session=%s", safe_id(session_id))
    return {"configurable": {"thread_id": session_id}}


def _interrupt_payload(result: dict):
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None

    value = getattr(interrupts[0], "value", None)
    return value if isinstance(value, dict) else None


def _update_workflow(
    session_id: str,
    state: dict,
    fallback: str = "",
):
    logger.info("workflow_state_received session=%s status=%s step=%s", safe_id(session_id), state.get("status"), state.get("current_step"))
    session = session_manager.get(session_id)

    session.workflow.update(
        {
            "status": state.get("status", "running"),
            "current_step": state.get("current_step", ""),
            "last_verified_step": state.get(
                "last_verified_step", ""
            ),
            "message": state.get("action_result") or fallback,
            "error": state.get("error"),
            "operation": state.get("operation"),
            "retry_count": state.get("retry_count", 0),
            "otp_required": bool(state.get("otp_required", False)),
            "otp_verified": bool(state.get("otp_verified", False)),
            "otp_invalid": bool(state.get("otp_invalid", False)),
            "challenge_id": state.get("otp_challenge_id") or session.otp_challenge_id,
            "target_site_url": (
                state.get("page_url")
                or (session.page.url if session.page else None)
            ),
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }
    )


# ============================================================
# APP LOGIN
# ============================================================
#
# IMPORTANT:
#
# This function ONLY authenticates the user against users.json
# and creates an application session.
#
# It MUST NOT:
#   - create Playwright
#   - open the target website
#   - call the LangGraph agent
#   - search for selectors
#   - ask for target-site OTP
#
# Browser automation starts only when the user clicks:
#   Punch In
#   Punch Out
#   Work From Home
#
# ============================================================

async def start_login(username: str):
    logger.info("application_login_started user=%s", safe_id(username))
    user = find_user(username)

    if not user:
        raise ValueError("User is not registered")

    # Create the application/browser session object only.
    #
    # NOTE:
    # If BrowserSessionManager.create() itself launches
    # Playwright in your project, replace this with a lightweight
    # application-session manager. For the current architecture,
    # create() should NOT launch the browser during app login.
    session = await session_manager.create()
    session.username = user["username"]

    password = get_target_password(user)

    # Save authenticated application state on the session.
    #
    # We deliberately do NOT call graph.ainvoke() here.
    state = {
        "session_id": session.session_id,
        "username": user["username"],
        "target_password": password,

        # This means application PIN authentication completed.
        # It does NOT mean target-site login completed.
        "operation": None,
        "status": "authenticated",
        "current_step": "app_authenticated",
        "last_verified_step": "app_authenticated",
        "retry_count": 0,
        "history": [],
        "error": None,
    }

    session.workflow.update(
        {
            "status": "authenticated",
            "current_step": "app_authenticated",
            "last_verified_step": "app_authenticated",
            "message": "Application login successful",
            "error": None,
            "operation": None,
            "retry_count": 0,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }
    )

    return {
        "session_id": session.session_id,
        "state": state,
        "interrupt": None,
        "authenticated": True,
        "browser_started": False,
        "message": "Login successful. Choose an attendance action.",
    }


# ============================================================
# TARGET-SITE LOGIN + OTP
# ============================================================
#
# This is called by the attendance workflow, not by app login.
#
# The attendance operation should start the graph from the
# app-authenticated state. The graph then:
#
#   1. Opens target site
#   2. Finds username
#   3. Enters username
#   4. Finds password
#   5. Enters password
#   6. Submits login
#   7. Handles post-login button
#   8. Waits for OTP
#   9. Interrupts for frontend OTP
#  10. Resumes after OTP
#
# ============================================================

async def start_target_login(
    session_id: str,
    operation: str,
    extra: dict | None = None,
):
    logger.info("target_login_started session=%s operation=%s", safe_id(session_id), operation)
    if operation not in {
        "punch_in",
        "punch_out",
        "work_from_home",
    }:
        raise ValueError(
            f"Unsupported operation: {operation}"
        )

    session = session_manager.get(session_id)

    async with session.operation_lock:
        
        # Browser starts ONLY for attendance operations.
        # Login does not start Playwright.
        await session_manager.start_browser(session_id)
        checkpoint = graph.get_state(
            config_for(session_id)
        )
        previous = dict(
            checkpoint.values or {}
        )

        # For a new application session there may not be a
        # LangGraph checkpoint yet. Build the initial state from
        # the authenticated application session.
        if not previous:
            username = session.username
            user = find_user(username or "")

            if not user:
                raise ValueError(
                    "Authenticated application user is unavailable"
                )

            previous = {
                "session_id": session_id,
                "username": user["username"],
                "target_password": get_target_password(
                    user
                ),
                "history": [],
            }

        state = dict(previous)

        already_authenticated = bool(
            getattr(session, "target_authenticated", False)
        )
        entry_step = (
            "authenticated" if already_authenticated else "app_authenticated"
        )

        state.update(
            {
                "session_id": session_id,
                "operation": operation,
                "status": "running",

                # The graph begins the target-site workflow from here.
                # If already authenticated on this browser session, skip
                # straight past login+OTP (see session.target_authenticated).
                "current_step": entry_step,
                "last_verified_step": entry_step,

                "retry_count": 0,
                "error": None,
                "recovery_reason": None,
                "force_inspect": False,
                "result": None,
                "otp_required": False,
                "otp_verified": False,
                "otp_invalid": False,
                "otp_challenge_id": session.otp_challenge_id,
                "otp_target_site_url": session.otp_target_site_url,
                "post_otp_target_site_url": None,
                "otp_attempt": session.otp_attempt,
            }
        )

        if extra:
            state.update(extra)

        _update_workflow(
            session_id,
            state,
            f"Starting {operation}",
        )

        try:
            result = await graph.ainvoke(
                state,
                config=config_for(session_id),
            )
        except Exception as exc:
            logger.exception("target_login_failed session=%s operation=%s", safe_id(session_id), operation)
            session.workflow.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "message": (
                        f"{operation} failed"
                    ),
                    "updated_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }
            )
            raise

        _update_workflow(
            session_id,
            dict(result),
            f"{operation} workflow running",
        )

        interrupt_payload = _interrupt_payload(
            result
        )

        if interrupt_payload:
            session.workflow.update(
                {
                    "status": "waiting_for_user",
                    "message": interrupt_payload.get(
                        "message",
                        "Waiting for OTP",
                    ),
                    "challenge_id": interrupt_payload.get(
                        "challenge_id"
                    ),
                }
            )

        return {
            "state": result,
            "interrupt": interrupt_payload,
        }


# ============================================================
# OTP
# ============================================================

async def resume_with_otp(
    session_id: str,
    challenge_id: str,
    otp: str,
):
    logger.info("otp_resume_started session=%s", safe_id(session_id))
    session = session_manager.get(session_id)

    if not otp.strip():
        raise ValueError(
            "OTP cannot be empty"
        )

    expected = session.otp_challenge_id

    if not expected or challenge_id != expected:
        raise ValueError(
            "Invalid or expired OTP challenge"
        )

    session.workflow.update(
        {
            "status": "running",
            "message": "OTP received; resuming target-site verification.",
            "error": None,
            "otp_required": False,
            "otp_invalid": False,
            "otp_verified": False,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }
    )

    result = await graph.ainvoke(
        Command(resume=otp.strip()),
        config=config_for(session_id),
    )
    logger.info("otp_resume_finished session=%s", safe_id(session_id))

    _update_workflow(
        session_id,
        dict(result),
        "OTP workflow resumed",
    )

    interrupt_payload = _interrupt_payload(
        result
    )

    if interrupt_payload:
        session.workflow.update(
            {
                "status": "waiting_for_user",
                "message": interrupt_payload.get(
                    "message",
                    "Waiting for OTP",
                ),
                "challenge_id": interrupt_payload.get(
                    "challenge_id"
                ),
            }
        )

    return {
        "state": result,
        "interrupt": interrupt_payload,
        "otp_verified": bool(result.get("otp_verified", False)),
        "otp_invalid": bool(result.get("otp_invalid", False)),
    }


# ============================================================
# ATTENDANCE OPERATIONS
# ============================================================

async def run_operation(
    session_id: str,
    operation: str,
    extra: dict | None = None,
):
    logger.info("operation_started session=%s operation=%s", safe_id(session_id), operation)
    if operation not in {
        "punch_in",
        "punch_out",
        "work_from_home",
    }:
        raise ValueError(
            f"Unsupported operation: {operation}"
        )

    # IMPORTANT:
    # Do NOT call session_manager.create() during app login.
    #
    # The existing session is used here.
    session = session_manager.get(session_id)

    async with session.operation_lock:

        # Browser starts ONLY when an attendance operation is requested.
        # Login itself does not launch Playwright.
        await session_manager.start_browser(session_id)

        # Try to retrieve the LangGraph checkpoint.
        checkpoint = graph.get_state(
            config_for(session_id)
        )

        previous = dict(
            checkpoint.values or {}
        )

        # If login only created an application session,
        # there may be no graph checkpoint yet.
        #
        # Build the graph's initial state here.
        if not previous:

            username = session.username

            if not username:
                raise ValueError(
                    "Authenticated user is not available"
                )

            user = find_user(username)

            if not user:
                raise ValueError(
                    "Authenticated user is not registered"
                )

            previous = {
                "session_id": session_id,
                "username": user["username"],
                "target_password": get_target_password(
                    user
                ),
                "history": [],
            }

        state = dict(previous)

        # --------------------------------------------------------
        # SKIP LOGIN + OTP WHEN ALREADY AUTHENTICATED
        # --------------------------------------------------------
        #
        # OTP is only required ONCE per browser session. If the
        # target site was already authenticated on this exact
        # Playwright page (see submit_otp / session.target_authenticated),
        # a new operation (e.g. Punch Out after Punch In) resumes
        # directly from "authenticated" instead of repeating
        # open_site -> username -> password -> OTP.
        #
        # If the browser/page had to be recreated (closed, crashed,
        # never logged in), target_authenticated is False and the
        # full login+OTP flow runs again.
        # --------------------------------------------------------

        already_authenticated = bool(
            getattr(session, "target_authenticated", False)
        )
        entry_step = (
            "authenticated" if already_authenticated else "app_authenticated"
        )

        logger.info(
            "operation_entry_point session=%s operation=%s already_authenticated=%s entry_step=%s",
            safe_id(session_id),
            operation,
            already_authenticated,
            entry_step,
        )

        state.update(
            {
                "session_id": session_id,
                "operation": operation,
                "status": "running",

                # IMPORTANT:
                # If the target site is already logged in on this
                # browser session, resume at "authenticated" so the
                # graph goes straight to click_me / click_time_attendance
                # for the new operation, without repeating login or OTP.
                # Otherwise the graph begins the full target-site
                # login workflow from the top.
                "current_step": entry_step,
                "last_verified_step": entry_step,

                "retry_count": 0,
                "error": None,
                "recovery_reason": None,
                "force_inspect": False,
                "result": None,
            }
        )

        if extra:
            state.update(extra)

        _update_workflow(
            session_id,
            state,
            f"Starting {operation}",
        )

        try:
            result = await graph.ainvoke(
                state,
                config=config_for(session_id),
            )
        except Exception as exc:
            logger.exception("operation_failed session=%s operation=%s", safe_id(session_id), operation)
            session.workflow.update(
                {
                    "status": "failed",
                    "error": str(exc),
                    "message": (
                        f"{operation} failed"
                    ),
                    "updated_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }
            )
            raise

        _update_workflow(
            session_id,
            dict(result),
            f"{operation} finished",
        )

        return {
            "state": result,
            "interrupt": _interrupt_payload(
                result
            ),
        }


# ============================================================
# SESSION STATUS
# ============================================================

def get_session_status(
    session_id: str,
) -> dict:
    logger.debug("session_status_requested session=%s", safe_id(session_id))
    session = session_manager.get(
        session_id
    )

    return {
        "session_id": session_id,
        **session.workflow,
    }


# ============================================================
# CLOSE SESSION
# ============================================================

async def close_session(
    session_id: str,
) -> None:
    logger.info("session_close_requested session=%s", safe_id(session_id))
    await session_manager.close(
        session_id
    )