import asyncio
import logging
import re
from datetime import datetime, timezone

from langgraph.types import interrupt
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from browser.helpers import (
    ATTENDANCE_SELECTORS,
    LOGIN_SELECTORS,
    NAV_SELECTORS,
    WFH_SELECTORS,
    page_snapshot,
    visible,
)
from browser.session import session_manager
from config import settings
from agent.llm import choose_action

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Session/page helpers
# ---------------------------------------------------------

def _session(state):
    logger.debug("agent_session_requested")
    return session_manager.get(state["session_id"])


def _page(state):
    session = _session(state)
    page = session.active_page()
    # Make it explicit in the logs which tab (main page vs. the tab opened
    # by Time & Attendance) every check/action actually runs against.
    which = "attendance_page" if page is session.attendance_page else "main_page"
    logger.debug(
        "agent_page_requested step=%s using=%s url=%s",
        state.get("current_step"),
        which,
        getattr(page, "url", None),
    )
    return page


def _page_open(page):
    return page is not None and not page.is_closed()


def _workflow(state, **values):
    session = _session(state)
    session.workflow.update(values)
    logger.info("workflow_updated step=%s status=%s", values.get("current_step", state.get("current_step")), values.get("status", state.get("status")))


async def _nav_visible(page, text: str, timeout: int = 5000) -> bool:
    """Check the existing target-site navigation selector without inventing selectors."""
    try:
        locator = (
            page.locator(NAV_SELECTORS["me"])
            .filter(
                has_text=re.compile(
                    rf"^\s*{re.escape(text)}\s*$",
                    re.IGNORECASE,
                )
            )
            .first
        )
        await locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        # The target site can render the same label with nested/extra text.
        # Keep the fallback text-based lookup generic and bounded; it does not
        # create a new CSS/XPath selector.
        try:
            locator = page.get_by_text(text, exact=True).first
            await locator.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False


def _inspection_checks(state):
    operation = state.get("operation")
    step = state.get("current_step", "")

    checks_by_step = {
        "site_opened": ["username_visible"],
        "username_entered": ["next_visible"],
        "next_clicked": ["password_visible"],
        "password_entered": ["sign_in_visible"],
        "signin_clicked": ["mail_visible"],
        "mail_clicked": ["otp_passcode_visible"],
        "post_login_button_clicked": [],
        "otp_received": [],
        "otp_entered": ["otp_submit_visible"],
        "otp_submitted": ["me_visible"],
        "authenticated": ["me_visible"],
        "me_clicked": ["time_attendance_visible"],
        "time_attendance_clicked": ["attendance_page_open"],
        "punch_in_clicked": ["confirm_punch_in_visible"],
        "punch_out_clicked": ["confirm_punch_out_visible"],
        "absence_management_clicked": ["absence_requests_visible"],
        "absence_requests_clicked": ["special_requests_visible"],
        "special_requests_clicked": ["apply_visible"],
        "apply_clicked": ["wfh_dropdown_visible"],
        "wfh_type_selected": ["reason_button_visible"],
        "end_date_entered": ["reason_button_visible"],
        "reason_dropdown_opened": ["others_visible"],
        "others_selected": ["reason_textbox_visible"],
        "wfh_reason_entered": ["wfh_submit_visible"],
    }

    if step == "app_authenticated":
        return []

    if step == "location_applied":
        return {
            "punch_in": ["punch_in_visible"],
            "punch_out": ["punch_out_visible"],
            "work_from_home": ["absence_management_visible"],
        }.get(operation, [])

    return checks_by_step.get(step, [])


async def _visible_by_label(page, label: str, timeout: int = 1500) -> bool:
    try:
        locator = page.get_by_label(label, exact=True).first
        await locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False


# ---------------------------------------------------------
# Deterministic inspection
# ---------------------------------------------------------

async def inspect(state):
    logger.info("agent_step_started step=inspect")
    session = _session(state)
    page = _page(state)

    # Log which tab (main login page vs. the tab Time & Attendance opened)
    # every check in this inspect() call is running against, so it's
    # obvious from the logs whether the "remaining" checks (Punch In,
    # Punch Out, Absence Management, etc.) are hitting the new page.
    which_page = "attendance_page" if page is session.attendance_page else "main_page"
    logger.info(
        "agent_step_inspecting using=%s url=%s",
        which_page,
        page.url,
    )

    snapshot = await page_snapshot(page)
    requested_checks = set(_inspection_checks(state))

    async def check(name, operation):
        if name not in requested_checks:
            return False
        # Most checks (e.g. `visible(...)`) are coroutine functions and must
        # be awaited. `_page_open` (and any other plain/sync check) returns
        # a plain bool immediately -- awaiting that raises
        # "TypeError: object bool can't be used in 'await' expression".
        # Support both without requiring every check to be async.
        result = operation()
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def nav_check(text):
        return await _nav_visible(page, text)

    # These checks are deliberately fixed. The LLM receives only booleans and
    # browser metadata, never raw HTML and never selector strings.
    check_operations = {
        "username_visible": lambda: visible(page, LOGIN_SELECTORS["username"]),
        "next_visible": lambda: visible(page, LOGIN_SELECTORS["next"]),
        "password_visible": lambda: visible(page, LOGIN_SELECTORS["password"]),
        "sign_in_visible": lambda: visible(page, LOGIN_SELECTORS["sign_in"]),
        "post_login_button_visible": lambda: visible(
            page, settings.POST_LOGIN_BUTTON_SELECTOR
        ),
        "otp_passcode_visible": lambda: _visible_by_label(page, "Passcode"),
        "mail_visible": lambda: visible(page, LOGIN_SELECTORS["mail"]),
        "otp_submit_visible": lambda: visible(page, LOGIN_SELECTORS["otp_submit"]),
        "me_visible": lambda: nav_check("Me"),
        "time_attendance_visible": lambda: nav_check("Time & Attendance"),
        "attendance_page_open": lambda: _page_open(session.attendance_page),
        "punch_in_visible": lambda: visible(page, ATTENDANCE_SELECTORS["punch_in"]),
        "punch_out_visible": lambda: visible(page, ATTENDANCE_SELECTORS["punch_out"]),
        "confirm_punch_in_visible": lambda: visible(
            page, ATTENDANCE_SELECTORS["confirm_punch_in"]
        ),
        "confirm_punch_out_visible": lambda: visible(
            page, ATTENDANCE_SELECTORS["confirm_punch_out"]
        ),
        "absence_management_visible": lambda: visible(
            page, WFH_SELECTORS["absence_management"]
        ),
        "absence_requests_visible": lambda: visible(
            page, WFH_SELECTORS["absence_requests"]
        ),
        "special_requests_visible": lambda: visible(
            page, WFH_SELECTORS["special_requests"]
        ),
        "apply_visible": lambda: visible(page, WFH_SELECTORS["apply"]),
        "wfh_dropdown_visible": lambda: visible(
            page, WFH_SELECTORS["request_type_dropdown"]
        ),
        "reason_button_visible": lambda: visible(page, WFH_SELECTORS["reason_button"]),
        "others_visible": lambda: visible(page, WFH_SELECTORS["others_option"]),
        "reason_textbox_visible": lambda: visible(
            page, WFH_SELECTORS["reason_textbox"]
        ),
        "wfh_submit_visible": lambda: visible(page, WFH_SELECTORS["submit"]),
    }

    names = list(requested_checks & check_operations.keys())
    results = await asyncio.gather(
        *(check(name, check_operations[name]) for name in names)
    )
    checks = dict(zip(names, results))

    logger.info("agent_step_finished step=inspect visible_checks=%s", sum(checks.values()))
    return {
        "page_url": snapshot["url"],
        "page_title": snapshot["title"],
        "checks": checks,
        "action_result": "inspection_complete",
        "error": None,
        "force_inspect": False,
    }


# ---------------------------------------------------------
# Login actions
# ---------------------------------------------------------

async def open_site(state):
    page = _session(state).page

    if not settings.TARGET_SITE_URL.strip():
        raise RuntimeError("TARGET_SITE_URL is empty in backend/.env")

    await page.goto(
        settings.TARGET_SITE_URL,
        wait_until="domcontentloaded",
        timeout=settings.ACTION_TIMEOUT_MS,
    )
    await page.locator(LOGIN_SELECTORS["username"]).wait_for(
        state="visible",
        timeout=settings.ACTION_TIMEOUT_MS,
    )

    return {
        "current_step": "site_opened",
        "action_result": "target_site_opened",
    }


async def enter_username(state):
    page = _session(state).page
    locator = page.locator(LOGIN_SELECTORS["username"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.fill(state["username"])

    actual = await locator.input_value()
    if actual.strip().lower() != state["username"].strip().lower():
        raise RuntimeError("Username verification failed")

    return {
        "current_step": "username_entered",
        "action_result": "username_entered_and_verified",
    }


async def click_next(state):
    page = _session(state).page
    locator = page.locator(LOGIN_SELECTORS["next"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.LOGIN_WAIT_MS)

    return {
        "current_step": "next_clicked",
        "action_result": "next_clicked",
    }


async def enter_password(state):
    page = _session(state).page
    locator = page.locator(LOGIN_SELECTORS["password"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.fill(state["target_password"])

    return {
        "current_step": "password_entered",
        "action_result": "target_password_entered",
    }


async def click_sign_in(state):
    page = _session(state).page
    locator = page.locator(LOGIN_SELECTORS["sign_in"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.POST_LOGIN_WAIT_MS)

    return {
        "current_step": "signin_clicked",
        "action_result": "sign_in_clicked",
    }


async def click_mail(state):
    page = _session(state).page

    # This selector comes directly from the known-good target-site script.
    locator = page.get_by_text("Send me an email", exact=True).first

    logger.info("Login: waiting for target-site 'Send me an email' button")
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.LOGIN_WAIT_MS)

    logger.info("Login: target-site 'Send me an email' clicked")

    return {
        "current_step": "mail_clicked",
        "action_result": "mail_clicked_otp_requested",
    }


async def click_post_login_button(state):
    page = _session(state).page
    locator = page.locator(settings.POST_LOGIN_BUTTON_SELECTOR).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.LOGIN_WAIT_MS)

    return {
        "current_step": "post_login_button_clicked",
        "action_result": "post_login_button_clicked",
    }


# ---------------------------------------------------------
# OTP
# ---------------------------------------------------------

async def request_otp(state):
    session = _session(state)
    page = session.page

    # Capture the URL of the TARGET SITE OTP page, never the frontend URL.
    passcode = page.get_by_label("Passcode").first
    await passcode.wait_for(
        state="visible",
        timeout=settings.ACTION_TIMEOUT_MS,
    )

    target_url = page.url
    session.otp_target_site_url = target_url
    session.otp_attempt = int(getattr(session, "otp_attempt", 0)) + 1
    challenge_id = f"{session.session_id}:otp:{session.otp_attempt}"
    session.otp_challenge_id = challenge_id

    logger.info(
        "OTP: target-site verification page ready; captured target-site URL=%s",
        target_url,
    )
    logger.info(
        "OTP: created challenge attempt=%s",
        session.otp_attempt,
    )

    return {
        "otp_required": True,
        "otp_challenge_id": challenge_id,
        "otp_target_site_url": target_url,
        "otp_attempt": session.otp_attempt,
        "current_step": "otp_waiting",
        "action_result": "target_site_otp_page_ready_waiting_for_frontend",
    }


async def wait_for_otp(state):
    session = _session(state)
    challenge_id = session.otp_challenge_id or state.get("otp_challenge_id")

    if not challenge_id:
        raise RuntimeError("OTP challenge is not available")

    payload = {
        "type": "otp_required",
        "challenge_id": challenge_id,
        "message": "Enter the OTP sent by the target website.",
    }

    otp = interrupt(payload)
    otp = str(otp).strip()

    if not otp:
        raise RuntimeError("OTP cannot be empty")

    return {
        "otp": otp,
        "otp_required": False,
        "otp_challenge_id": challenge_id,
        "current_step": "otp_received",
        "action_result": "otp_received_from_frontend",
    }


async def enter_otp(state):
    page = _session(state).page

    try:
        await page.get_by_label("Passcode").fill(state["otp"])
    except Exception:
        candidate_selectors = [
            "sdf-input#otp-page_passcode input#input",
            "input[name=\"otp\"]",
            "input[aria-label=\"Passcode\" i]",
            "[role=\"textbox\"][name=\"Passcode\"]",
        ]

        locator = None
        for selector in candidate_selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=3000)
                break
            except Exception:
                continue

        if locator is None:
            raise RuntimeError("OTP passcode input was not found on the target page")

        await locator.fill(state["otp"])

    return {
        "current_step": "otp_entered",
        "action_result": "otp_entered",
    }


async def submit_otp(state):
    session = _session(state)
    page = session.page
    baseline_url = (
        session.otp_target_site_url
        or state.get("otp_target_site_url")
        or page.url
    )

    logger.info("OTP: entering submit step on target site")
    logger.info("OTP: target-site URL before Submit=%s", baseline_url)

    # This selector comes directly from the known-good target-site script.
    submit_otp_button = page.get_by_text("Submit", exact=True).first
    await submit_otp_button.wait_for(
        state="visible",
        timeout=settings.ACTION_TIMEOUT_MS,
    )
    await submit_otp_button.click(timeout=10000)
    logger.info("OTP: target-site Submit clicked")

    # ------------------------------------------------------------
    # IMPORTANT: do not sleep a fixed amount of time and check the
    # URL exactly once. Enterprise SSO / attendance sites often do
    # several redirects after Submit, and the final hop to
    # /dashboard can land after POST_LOGIN_WAIT_MS has already
    # elapsed. Checking only once at a fixed delay caused a valid
    # OTP to be reported as "not accepted" simply because the
    # dashboard redirect hadn't finished yet.
    #
    # Instead, actively poll the page URL until it reaches
    # /dashboard or the action timeout is hit.
    # ------------------------------------------------------------

    dashboard_pattern = re.compile(
        r"/dashboard(?:[/?#].*)?$",
        re.IGNORECASE,
    )

    poll_interval_ms = 300
    elapsed_ms = 0
    current_url = page.url
    dashboard_url = bool(dashboard_pattern.search(current_url))

    while not dashboard_url and elapsed_ms < settings.ACTION_TIMEOUT_MS:
        await page.wait_for_timeout(poll_interval_ms)
        elapsed_ms += poll_interval_ms
        current_url = page.url
        dashboard_url = bool(dashboard_pattern.search(current_url))

    logger.info(
        "OTP: target-site URL after Submit=%s (waited %sms, dashboard_reached=%s)",
        current_url,
        elapsed_ms,
        dashboard_url,
    )

    # OTP success is deliberately deterministic: the target site must reach
    # /dashboard. A URL change to some other page is NOT treated as success.
    # The frontend URL is never involved in this check.

    if not dashboard_url:
        session.otp_target_site_url = current_url
        logger.warning(
            "OTP: target-site URL did not reach /dashboard; requesting OTP again"
        )
        return {
            "otp_required": True,
            "otp_verified": False,
            "otp_invalid": True,
            "otp_challenge_id": session.otp_challenge_id,
            "otp_target_site_url": baseline_url,
            "post_otp_target_site_url": current_url,
            "otp_attempt": session.otp_attempt,
            "current_step": "otp_waiting",
            "action_result": "otp_not_accepted_reenter_otp",
        }

    logger.info(
        "OTP: target-site reached /dashboard; OTP accepted"
    )
    session.otp_target_site_url = baseline_url

    # Give the dashboard a brief moment to finish rendering (nav links etc.)
    # before the next step looks for "Me".
    await page.wait_for_timeout(settings.POST_LOGIN_WAIT_MS)

    # OTP is only required ONCE per browser session/page. Later Punch In,
    # Punch Out or WFH operations reuse this authenticated page and skip
    # the entire login+OTP sequence (see agent_service.run_operation).
    session.target_authenticated = True

    return {
        "current_step": "otp_submitted",
        "otp_verified": True,
        "otp_invalid": False,
        "otp_required": False,
        "action_result": "otp_verified_target_site_dashboard_reached",
        "otp_target_site_url": baseline_url,
        "post_otp_target_site_url": current_url,
    }


# ---------------------------------------------------------
# Navigation
# ---------------------------------------------------------

async def click_me(state):
    page = _session(state).page
    locator = (
        page.locator(NAV_SELECTORS["me"])
        .filter(has_text=re.compile(r"^\s*Me\s*$"))
        .first
    )
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.LOGIN_WAIT_MS)

    return {
        "current_step": "me_clicked",
        "action_result": "me_clicked",
    }


async def click_time_attendance(state):
    session = _session(state)
    page = session.page

    # --------------------------------------------------------
    # Defense against duplicate tabs.
    #
    # If a previous attempt already opened a Time & Attendance tab (e.g. a
    # retry after a transient/verification error), reuse or close it instead
    # of clicking again and letting the target site open yet another tab.
    # Each click on this nav link opens a NEW popup on this site, so retrying
    # the click without cleaning up the old tab is what caused 3-4 tabs to
    # pile up with different URLs.
    # --------------------------------------------------------
    existing = session.attendance_page
    if existing is not None and existing is not page and not existing.is_closed():
        try:
            await existing.close()
            logger.info("Time & Attendance: closed a stale tab before retrying")
        except Exception:
            logger.exception("Time & Attendance: failed to close stale tab")
    session.attendance_page = None

    locator = (
        page.locator(NAV_SELECTORS["time_attendance"])
        .filter(has_text=re.compile(r"^\s*Time & Attendance\s*$"))
        .first
    )
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)

    # Time & Attendance may open a popup/new tab or navigate the current page.
    attendance_page = None
    try:
        async with page.expect_popup(timeout=5000) as popup_info:
            await locator.click(timeout=10000)
        attendance_page = await popup_info.value
    except PlaywrightTimeoutError:
        # The click already happened. No popup means the site navigated the
        # existing page (or opened the content without a popup). Do not click twice.
        attendance_page = page

    session.attendance_page = attendance_page

    try:
        await attendance_page.wait_for_load_state(
            "domcontentloaded", timeout=settings.ACTION_TIMEOUT_MS
        )
    except Exception:
        pass

    # --------------------------------------------------------
    # Catch the FINAL url, not an intermediate redirect hop.
    #
    # This target site's Time & Attendance tab redirects through more than
    # one URL before landing on its real destination (seen in production:
    # .../V7/ess/dashboard -> .../infoservices.securtime.adp.com/ng/dashboard).
    # "domcontentloaded" only guarantees the FIRST hop finished, so capturing
    # attendance_page.url right after it can grab a transitional URL.
    #
    # Poll the URL until it stops changing (settles) or the action timeout
    # is hit, so downstream steps (Punch In / Punch Out / Absence
    # Management) see the real, final page.
    # --------------------------------------------------------
    settle_check_ms = 400
    stable_reads_required = 2
    elapsed_ms = 0
    stable_reads = 0
    last_url = attendance_page.url

    while (
        stable_reads < stable_reads_required
        and elapsed_ms < settings.ACTION_TIMEOUT_MS
    ):
        await attendance_page.wait_for_timeout(settle_check_ms)
        elapsed_ms += settle_check_ms
        current_url = attendance_page.url
        if current_url == last_url:
            stable_reads += 1
        else:
            logger.info(
                "Time & Attendance: URL changed mid-redirect %s -> %s",
                last_url,
                current_url,
            )
            stable_reads = 0
            last_url = current_url

    logger.info(
        "Time & Attendance: settled on URL=%s (waited %sms)",
        last_url,
        elapsed_ms,
    )

    # Give the final page a moment to finish rendering its own content
    # (nav links, Punch In / absence management buttons, etc.).
    await attendance_page.wait_for_timeout(settings.ATTENDANCE_RENDER_WAIT_MS)

    return {
        "current_step": "time_attendance_clicked",
        "action_result": "time_attendance_page_opened",
        "page_url": attendance_page.url,
        "page_title": await attendance_page.title(),
    }


# ---------------------------------------------------------
# Location
# ---------------------------------------------------------

async def apply_location(state):
    if state.get("latitude") is None or state.get("longitude") is None:
        raise RuntimeError("Current browser location is required")

    session = _session(state)
    page = session.active_page()

    await session.apply_location(
        {
            "latitude": state["latitude"],
            "longitude": state["longitude"],
            "accuracy": state.get("accuracy"),
            "captured_at": state.get("captured_at"),
        },
        page,
    )

    return {
        "current_step": "location_applied",
        "action_result": "user_location_applied_to_playwright",
    }


# ---------------------------------------------------------
# Punch In / Punch Out
# ---------------------------------------------------------

async def click_punch_in(state):
    page = _page(state)
    session = _session(state)

    # Frontend-supplied location is workflow data, not an LLM decision.
    if state.get("latitude") is None or state.get("longitude") is None:
        raise RuntimeError("Current browser location is required")

    logger.info(
        "punch_in_location_ready session=%s",
        session.session_id[:8],
    )
    await session.apply_location(
        {
            "latitude": state["latitude"],
            "longitude": state["longitude"],
            "accuracy": state.get("accuracy"),
            "captured_at": state.get("captured_at"),
        },
        page=page,
    )

    locator = page.locator(ATTENDANCE_SELECTORS["punch_in"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.PUNCH_CONFIRM_WAIT_MS)

    return {
        "current_step": "punch_in_clicked",
        "action_result": "punch_in_clicked_confirmation_expected",
    }


async def confirm_punch_in(state):
    page = _page(state)
    session = _session(state)

    # Re-apply the exact location supplied by the frontend immediately before
    # the target-site confirmation click.
    if state.get("latitude") is None or state.get("longitude") is None:
        raise RuntimeError("Current browser location is required")

    logger.info(
        "confirm_punch_in_location_ready session=%s",
        session.session_id[:8],
    )
    await session.apply_location(
        {
            "latitude": state["latitude"],
            "longitude": state["longitude"],
            "accuracy": state.get("accuracy"),
            "captured_at": state.get("captured_at"),
        },
        page=page,
    )

    locator = page.locator(ATTENDANCE_SELECTORS["confirm_punch_in"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.PUNCH_CONFIRM_WAIT_MS)

    return {
        "current_step": "punch_in_completed",
        "status": "completed",
        "result": {
            "operation": "punch_in",
            "status": "completed",
            "location": _session(state).location,
        },
        "action_result": "punch_in_confirmed",
    }


async def click_punch_out(state):
    page = _page(state)
    session = _session(state)

    # Frontend-supplied location is workflow data, not an LLM decision.
    if state.get("latitude") is None or state.get("longitude") is None:
        raise RuntimeError("Current browser location is required")

    logger.info(
        "punch_out_location_ready session=%s",
        session.session_id[:8],
    )
    await session.apply_location(
        {
            "latitude": state["latitude"],
            "longitude": state["longitude"],
            "accuracy": state.get("accuracy"),
            "captured_at": state.get("captured_at"),
        },
        page=page,
    )

    locator = page.locator(ATTENDANCE_SELECTORS["punch_out"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.PUNCH_CONFIRM_WAIT_MS)

    return {
        "current_step": "punch_out_clicked",
        "action_result": "punch_out_clicked_confirmation_expected",
    }


async def confirm_punch_out(state):
    page = _page(state)
    session = _session(state)

    # Re-apply the exact location supplied by the frontend immediately before
    # the target-site confirmation click.
    if state.get("latitude") is None or state.get("longitude") is None:
        raise RuntimeError("Current browser location is required")

    logger.info(
        "confirm_punch_out_location_ready session=%s",
        session.session_id[:8],
    )
    await session.apply_location(
        {
            "latitude": state["latitude"],
            "longitude": state["longitude"],
            "accuracy": state.get("accuracy"),
            "captured_at": state.get("captured_at"),
        },
        page=page,
    )

    locator = page.locator(ATTENDANCE_SELECTORS["confirm_punch_out"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.PUNCH_CONFIRM_WAIT_MS)

    return {
        "current_step": "punch_out_completed",
        "status": "completed",
        "result": {
            "operation": "punch_out",
            "status": "completed",
            "location": _session(state).location,
        },
        "action_result": "punch_out_confirmed",
    }


# ---------------------------------------------------------
# Work From Home
# ---------------------------------------------------------

async def click_absence_management(state):
    page = _page(state)
    session = _session(state)

    # WFH also uses the frontend-supplied location. This remains backend-only.
    if state.get("latitude") is None or state.get("longitude") is None:
        raise RuntimeError("Current browser location is required")

    await session.apply_location(
        {
            "latitude": state["latitude"],
            "longitude": state["longitude"],
            "accuracy": state.get("accuracy"),
            "captured_at": state.get("captured_at"),
        },
        page=page,
    )

    locator = page.locator(WFH_SELECTORS["absence_management"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.WFH_WAIT_MS)
    return {
        "current_step": "absence_management_clicked",
        "action_result": "absence_management_clicked",
    }


async def click_absence_requests(state):
    page = _page(state)
    locator = page.locator(WFH_SELECTORS["absence_requests"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.WFH_WAIT_MS)
    return {
        "current_step": "absence_requests_clicked",
        "action_result": "absence_requests_clicked",
    }


async def click_special_requests(state):
    page = _page(state)
    locator = page.get_by_text(" Special Requests", exact=True).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)

    # WFH-specific delay:
    # after clicking "Special Requests", the target site needs about
    # 5 seconds to render the next controls.
    await page.wait_for_timeout(5000)

    return {
        "current_step": "special_requests_clicked",
        "action_result": "special_requests_clicked",
    }


async def click_apply(state):
    page = _page(state)
    locator = page.get_by_text(" Apply", exact=True).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(no_wait_after=True, timeout=10000)
    await page.wait_for_timeout(settings.WFH_WAIT_MS)
    return {
        "current_step": "apply_clicked",
        "action_result": "apply_clicked",
    }


async def select_work_from_home(state):
    page = _page(state)
    dropdown = page.get_by_role("button", name="Select one...").first
    await dropdown.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await dropdown.click(timeout=10000)

    option = page.get_by_role("option", name="Work From Home").first
    await option.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await option.click(timeout=10000)
    await page.wait_for_timeout(settings.WFH_WAIT_MS)

    return {
        "current_step": "wfh_type_selected",
        "action_result": "work_from_home_selected",
    }


def _normalise_date_for_input(value: str, input_type: str) -> str:
    """Use ISO for HTML date inputs; preserve dd/mm/yyyy for text inputs."""
    value = value.strip()
    if input_type != "date":
        return value

    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        day, month, year = value.split("/")
        return f"{year}-{month}-{day}"

    return value


async def _fill_date(page, index: int, value: str):
    inputs = page.locator(WFH_SELECTORS["date_input"])
    locator = inputs.nth(index)
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)

    input_type = await locator.get_attribute("type") or "text"
    formatted = _normalise_date_for_input(value, input_type)
    await locator.fill(formatted)

    actual = await locator.input_value()
    if not actual:
        raise RuntimeError("Date value was not accepted by the target site")


async def enter_start_date(state):
    page = _page(state)
    await _fill_date(page, 1, state["start_date"])
    await page.wait_for_timeout(settings.WFH_WAIT_MS)
    return {
        "current_step": "start_date_entered",
        "action_result": "start_date_entered",
    }


async def enter_end_date(state):
    page = _page(state)
    await _fill_date(page, 2, state["end_date"])
    await page.wait_for_timeout(settings.WFH_WAIT_MS)
    return {
        "current_step": "end_date_entered",
        "action_result": "end_date_entered",
    }


async def select_reason(state):
    page = _page(state)
    locator = page.get_by_role(
        "button", name=re.compile("Reason", re.IGNORECASE)
    ).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.WFH_WAIT_MS)
    return {
        "current_step": "reason_dropdown_opened",
        "action_result": "reason_dropdown_opened",
    }


async def select_others(state):
    page = _page(state)
    locator = page.get_by_role("option", name="Others").first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.WFH_WAIT_MS)
    return {
        "current_step": "others_selected",
        "action_result": "others_selected",
    }


async def enter_wfh_reason(state):
    page = _page(state)
    locator = page.get_by_role("textbox", name="Enter Reason").first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.fill(state["reason"])
    await locator.press("Tab")
    await page.wait_for_timeout(settings.WFH_WAIT_MS)

    return {
        "current_step": "wfh_reason_entered",
        "action_result": "wfh_reason_entered",
    }


async def submit_wfh(state):
    page = _page(state)
    locator = page.locator(WFH_SELECTORS["submit"]).first
    await locator.wait_for(state="visible", timeout=settings.ACTION_TIMEOUT_MS)
    await locator.click(timeout=10000)
    await page.wait_for_timeout(settings.WFH_WAIT_MS)

    return {
        "current_step": "wfh_submitted",
        "status": "completed",
        "result": {
            "operation": "work_from_home",
            "status": "submitted",
            "start_date": state["start_date"],
            "end_date": state["end_date"],
            "reason": state["reason"],
            "location": _session(state).location,
        },
        "action_result": "wfh_submit_clicked",
    }


# ---------------------------------------------------------
# Action registry
# ---------------------------------------------------------

# These are the resulting states that Python can deterministically verify.
STEP_EXPECTATIONS = {
    "site_opened": ["username_visible"],
    "username_entered": ["next_visible"],
    "next_clicked": ["password_visible"],
    "password_entered": ["sign_in_visible"],
    "signin_clicked": ["mail_visible"],
    "mail_clicked": ["otp_passcode_visible"],
    "post_login_button_clicked": [],
    "otp_entered": ["otp_submit_visible"],
    "otp_submitted": ["me_visible"],
    "me_clicked": ["time_attendance_visible"],
    "time_attendance_clicked": ["attendance_page_open"],
    "location_applied": [],
    "punch_in_clicked": ["confirm_punch_in_visible"],
    "punch_out_clicked": ["confirm_punch_out_visible"],
    "confirm_punch_in": [],
    "confirm_punch_out": [],
    "absence_management_clicked": ["absence_requests_visible"],
    "absence_requests_clicked": ["special_requests_visible"],
    "special_requests_clicked": ["apply_visible"],
    "apply_clicked": ["wfh_dropdown_visible"],
    "wfh_type_selected": ["reason_button_visible"],
    "start_date_entered": [],
    "end_date_entered": ["reason_button_visible"],
    "reason_dropdown_opened": ["others_visible"],
    "others_selected": ["reason_textbox_visible"],
    "wfh_reason_entered": ["wfh_submit_visible"],
    "wfh_submitted": [],
    "punch_in_completed": [],
    "punch_out_completed": [],
}


async def _verify_candidate_step(state, candidate_step: str) -> tuple[bool, dict]:
    inspection = await inspect(state)
    checks = inspection.get("checks", {})
    expected = STEP_EXPECTATIONS.get(candidate_step, [])

    if candidate_step == "location_applied":
        ok = _session(state).location is not None
    elif not expected:
        # Final confirmation actions have no stable success selector supplied by
        # the target site. The Playwright click itself succeeded, so accept it.
        ok = True
    else:
        ok = all(bool(checks.get(name)) for name in expected)

    logger.info("agent_step_verified step=%s verified=%s", candidate_step, ok)
    return ok, inspection


