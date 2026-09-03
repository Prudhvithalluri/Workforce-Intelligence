import logging
import re
from datetime import datetime, timezone

from config import settings

logger = logging.getLogger(__name__)

LOGIN_SELECTORS = {
    "username": '#login-form_username #input',
    "next": 'text="Next"',
    "password": '#login-form_password #input',
    "sign_in": 'text="Sign in"',
    "mail": 'text="Send me an email"',
    "otp_submit": 'text="Submit"',
}

NAV_SELECTORS = {
    "me": 'div.label',
    "time_attendance": 'div.label',
}

ATTENDANCE_SELECTORS = {
    "punch_in": 'sdf-button[aria-label="Punch In"]',
    "confirm_punch_in": 'text="Confirm punch in"',
    "punch_out": 'sdf-button[aria-label="Punch Out"]',
    "confirm_punch_out": 'text="Confirm punch out"',
}

WFH_SELECTORS = {
    "absence_management": 'a[data-id="absence-management-AM"]',
    "absence_requests": 'a[data-id="absence-requests-AM-am-requests"]',
    "special_requests": 'text=" Special Requests"',
    "apply": 'text=" Apply"',
    # Primary: the real clickable element inside the custom
    # <sdf-select-simple label="Select Type"> component, confirmed via
    # DevTools inspection.
    "select_type_trigger": 'sdf-select-simple[label="Select Type"] div.trigger-button',
    # Fallback only: relies on the component exposing a proper
    # accessible role/name, which may not hold if it uses a closed
    # shadow root. Kept only as a last resort, not the primary path.
    "request_type_dropdown": 'role=button[name="Select one..."]',
    "wfh_option": 'role=option[name="Work From Home"]',
    "date_input": 'input[name="sdf-input"]',
    "reason_button": 'role=button[name=/Reason/i]',
    "others_option": 'role=option[name="Others"]',
    "reason_textbox": 'role=textbox[name="Enter Reason"]',
    "submit": 'text="Submit"',
}


async def visible(page, selector: str, timeout: int = 1500) -> bool:
    logger.debug("selector_visibility_check timeout_ms=%s", timeout)
    try:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        logger.debug("selector_not_visible")
        return False


async def page_snapshot(page) -> dict:
    logger.debug("page_snapshot_started")
    try:
        title = await page.title()
    except Exception:
        title = ""
    logger.debug("page_snapshot_finished title_present=%s", bool(title))
    return {"url": page.url, "title": title}
