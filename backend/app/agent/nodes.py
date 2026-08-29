import logging
from datetime import datetime, timezone

from agent.llm import choose_action
from agent.common_steps import (
    _session,
    _workflow,
    inspect,
    _verify_candidate_step,
    open_site,
    enter_username,
    click_next,
    enter_password,
    click_sign_in,
    click_mail,
    request_otp,
    wait_for_otp,
    enter_otp,
    submit_otp,
    click_me,
    click_time_attendance,
)
from agent.punch_in import ACTIONS as PUNCH_IN_ACTIONS
from agent.punch_out import ACTIONS as PUNCH_OUT_ACTIONS
from agent.wfh import ACTIONS as WFH_ACTIONS
from config import settings

logger = logging.getLogger(__name__)

COMMON_ACTIONS = {
    "open_site": open_site,
    "enter_username": enter_username,
    "click_next": click_next,
    "enter_password": enter_password,
    "click_sign_in": click_sign_in,
    "click_mail": click_mail,
    "request_otp": request_otp,
    "wait_for_otp": wait_for_otp,
    "enter_otp": enter_otp,
    "submit_otp": submit_otp,
    "click_me": click_me,
    "click_time_attendance": click_time_attendance,
}

ACTION_FUNCTIONS = {**COMMON_ACTIONS, **PUNCH_IN_ACTIONS, **PUNCH_OUT_ACTIONS, **WFH_ACTIONS}

COMMON_FLOW = {
    "": ["open_site"], "app_authenticated": ["open_site"],
    "site_opened": ["enter_username"], "username_entered": ["click_next"],
    "next_clicked": ["enter_password"], "password_entered": ["click_sign_in"],
    "signin_clicked": ["click_mail"], "mail_clicked": ["request_otp"],
    "otp_waiting": ["wait_for_otp"], "otp_received": ["enter_otp"],
    "otp_entered": ["submit_otp"], "otp_submitted": ["click_me"],
    "authenticated": ["click_me"], "me_clicked": ["click_time_attendance"],
}
OPERATION_NEXT = {
    "punch_in": {"time_attendance_clicked": ["click_punch_in"], "punch_in_clicked": ["confirm_punch_in"]},
    "punch_out": {"time_attendance_clicked": ["click_punch_out"], "punch_out_clicked": ["confirm_punch_out"]},
    "work_from_home": {
        "time_attendance_clicked":["click_absence_management"], "absence_management_clicked":["click_absence_requests"],
        "absence_requests_clicked":["click_special_requests"], "special_requests_clicked":["click_apply"],
        "apply_clicked":["select_work_from_home"], "wfh_type_selected":["enter_start_date"],
        "start_date_entered":["enter_end_date"], "end_date_entered":["select_reason"],
        "reason_dropdown_opened":["select_others"], "others_selected":["enter_wfh_reason"],
        "wfh_reason_entered":["submit_wfh"],
    },
}

ACTION_TO_STEP = {
    "open_site": "site_opened",
    "enter_username": "username_entered",
    "click_next": "next_clicked",
    "enter_password": "password_entered",
    "click_sign_in": "signin_clicked",
    "click_mail": "mail_clicked",
    "request_otp": "otp_waiting",
    "wait_for_otp": "otp_received",
    "enter_otp": "otp_entered",
    "submit_otp": "otp_submitted",
    "click_me": "me_clicked",
    "click_time_attendance": "time_attendance_clicked",
    "click_punch_in": "punch_in_clicked",
    "confirm_punch_in": "punch_in_completed",
    "click_punch_out": "punch_out_clicked",
    "confirm_punch_out": "punch_out_completed",
    "click_absence_management": "absence_management_clicked",
    "click_absence_requests": "absence_requests_clicked",
    "click_special_requests": "special_requests_clicked",
    "click_apply": "apply_clicked",
    "select_work_from_home": "wfh_type_selected",
    "enter_start_date": "start_date_entered",
    "enter_end_date": "end_date_entered",
    "select_reason": "reason_dropdown_opened",
    "select_others": "others_selected",
    "enter_wfh_reason": "wfh_reason_entered",
    "submit_wfh": "wfh_submitted",
}

def available_actions(state):
    if state.get("force_inspect"): return ["inspect"]
    step=state.get("current_step", "")
    if step in COMMON_FLOW:
        actions = COMMON_FLOW[step]
    else:
        actions = OPERATION_NEXT.get(
            state.get("operation"),
            {},
        ).get(step, [])
    logger.info("agent_actions_available step=%s operation=%s actions=%s", step, state.get("operation"), actions)
    return actions

# ---------------------------------------------------------
# LLM brain node
# ---------------------------------------------------------

async def decide_and_execute(state):
    logger.info("agent_decision_started step=%s", state.get("current_step"))
    inspection = await inspect(state)
    working_state = {**state, **inspection}

    actions = available_actions(working_state)
    if not actions:
        raise RuntimeError(
            f"No valid action is available for step '{working_state.get('current_step')}'"
        )

    # The LLM is the workflow decision-maker for every executable step, even
    # when only one action is currently legal. Python still constrains the
    # candidate list so the model cannot invent or skip actions.
    logger.info(
        "LLM decision required step=%s available_actions=%s",
        working_state.get("current_step"),
        actions,
    )
    decision = await choose_action(working_state, actions)
    action = decision["action"]
    reason = decision.get("reason", "")

    logger.info("agent_action_selected action=%s", action)

    if action == "inspect":
        return {
            **working_state,
            "action": "inspect",
            "action_result": "inspection_complete",
            "error": None,
        }

    previous_verified = working_state.get("last_verified_step", "")
    retry_count = int(working_state.get("retry_count", 0))

    _workflow(
        working_state,
        status="running",
        current_step=working_state.get("current_step", ""),
        last_verified_step=previous_verified,
        message=f"LLM selected {action}",
        error=None,
        operation=working_state.get("operation"),
        retry_count=retry_count,
    )

    try:
        result = await ACTION_FUNCTIONS[action](working_state)
        logger.info("agent_action_finished action=%s", action)
        candidate_step = result.get("current_step", working_state.get("current_step", ""))

        # OTP is a deliberate pause. Verification continues after the user resumes.
        if result.get("otp_required"):
            _workflow(
                working_state,
                status="waiting_for_user",
                current_step=candidate_step,
                last_verified_step=previous_verified,
                message="Waiting for OTP from the frontend",
                error=None,
                retry_count=retry_count,
            )
            return {
                **working_state,
                **result,
                "action": action,
                "error": None,
                "otp_invalid": bool(result.get("otp_invalid", False)),
                "otp_verified": bool(result.get("otp_verified", False)),
                "history": [{
                    "time": datetime.now(timezone.utc).isoformat(),
                    "action": action,
                    "reason": reason,
                    "verified": True,
                    "step": candidate_step,
                }],
            }

        verified, inspection_after = await _verify_candidate_step(
            {**working_state, **result}, candidate_step
        )

        if not verified:
            raise RuntimeError(
                f"Step '{candidate_step}' ran, but its expected UI state was not verified"
            )

        new_status = result.get("status", "running")
        new_last_verified = candidate_step

        _workflow(
            working_state,
            status=new_status,
            current_step=candidate_step,
            last_verified_step=new_last_verified,
            message=result.get("action_result", action),
            error=None,
            retry_count=0,
        )

        return {
            **working_state,
            **result,
            **inspection_after,
            "action": action,
            "error": None,
            "retry_count": 0,
            "last_verified_step": new_last_verified,
            "failed_action": None,
            "failed_step": None,
            "recovery_checks": {},
            "history": [{
                "time": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "reason": reason,
                "verified": True,
                "step": candidate_step,
            }],
        }

    except Exception as exc:
        logger.exception("agent_action_failed action=%s", action)
        retry = retry_count + 1

        # Recovery never assumes that a failed Playwright call means the UI
        # action did not happen. Some target-site controls can perform the
        # action and then time out while waiting for the response. Check the
        # failed action's expected next-state selector before rewinding.
        failed_step = ACTION_TO_STEP.get(action, "")
        failed_verified = False
        recovery_checks = {}
        if failed_step:
            try:
                failed_verified, failed_inspection = await _verify_candidate_step(
                    {**working_state, "action": action}, failed_step
                )
                recovery_checks = failed_inspection.get("checks", {})
            except Exception:
                logger.exception("recovery_state_check_failed action=%s step=%s", action, failed_step)

        recovery_step = failed_step if failed_verified else previous_verified
        recovery_message = (
            f"{action} reported an error, but its expected state '{failed_step}' "
            "is visible; continuing from that verified state"
            if failed_verified
            else f"{action} failed; re-checking from previous verified step '{previous_verified}'"
        )

        _workflow(
            working_state,
            status="recovering" if retry < settings.MAX_AGENT_RETRIES else "failed",
            current_step=recovery_step,
            last_verified_step=recovery_step,
            message=recovery_message,
            error=str(exc),
            retry_count=retry,
            failed_action=action,
            failed_step=failed_step,
            recovery_checks=recovery_checks,
        )

        return {
            **working_state,
            "current_step": recovery_step,
            "last_verified_step": recovery_step,
            "retry_count": retry,
            "action": action,
            "action_result": "action_failed_and_recovery_required",
            "error": str(exc),
            "failed_action": action,
            "failed_step": failed_step,
            "recovery_checks": recovery_checks,
            "recovery_reason": recovery_message,
            "force_inspect": False,
            "history": [{
                "time": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "reason": reason,
                "verified": failed_verified,
                "step": recovery_step,
                "error": str(exc),
            }],
        }


async def recover(state):
    logger.info("agent_recovery_started retries=%s", state.get("retry_count", 0))
    retry = int(state.get("retry_count", 0))
    last_verified = state.get("last_verified_step", "")

    if retry >= settings.MAX_AGENT_RETRIES:
        _workflow(
            state,
            status="failed",
            current_step=last_verified,
            last_verified_step=last_verified,
            message="Maximum recovery attempts reached",
            error=state.get("error"),
            retry_count=retry,
        )
        return {
            **state,
            "status": "failed",
        }

    # On the next decide node, inspection happens first. The LLM then chooses
    # the next predefined action from the recovered step.
    _workflow(
        state,
        status="recovering",
        current_step=last_verified,
        last_verified_step=last_verified,
        message=f"Checking previous verified step: {last_verified or 'initial state'}",
        error=None,
        retry_count=retry,
    )

    return {
        **state,
        "current_step": last_verified,
        "error": None,
        "recovery_reason": f"Recovered to {last_verified or 'initial state'}",
        "force_inspect": False,
    }


async def start_or_continue(state):
    logger.info("agent_workflow_started operation=%s", state.get("operation"))
    if not state.get("current_step"):
        return {
            **state,
            "status": "running",
            "retry_count": int(state.get("retry_count", 0)),
            "error": None,
        }
    return state


async def finalize_if_complete(state):
    logger.info("agent_workflow_finalized status=%s", state.get("status"))
    session = _session(state)

    if state.get("status") == "failed":
        _workflow(
            state,
            status="failed",
            current_step=state.get("current_step", ""),
            last_verified_step=state.get("last_verified_step", ""),
            message=state.get("error") or "Automation failed",
            error=state.get("error"),
            retry_count=state.get("retry_count", 0),
        )
        return state

    if state.get("status") == "completed":
        _workflow(
            state,
            status="completed",
            current_step=state.get("current_step", ""),
            last_verified_step=state.get("last_verified_step", ""),
            message=state.get("action_result") or "Completed",
            error=None,
            retry_count=0,
        )
        return state

    # Login is authenticated once OTP is submitted and the post-login page is
    # verified by the otp_submitted expectation (Me visible).
    if (
        state.get("operation") == "login"
        and state.get("current_step") == "otp_submitted"
        and not state.get("error")
    ):
        result = {
            **state,
            "status": "completed",
            "current_step": "authenticated",
            "last_verified_step": "authenticated",
            "result": {"operation": "login", "status": "authenticated"},
            "action_result": "target_site_login_completed",
        }
        _workflow(
            result,
            status="completed",
            current_step="authenticated",
            last_verified_step="authenticated",
            message="Target-site login completed",
            error=None,
            retry_count=0,
        )
        return result

    return state
