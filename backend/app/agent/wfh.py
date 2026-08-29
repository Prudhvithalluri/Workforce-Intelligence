"""Operation-specific target-site steps. Browser actions are implemented in common_steps.py."""
from agent.common_steps import click_absence_management, click_absence_requests, click_special_requests, click_apply, select_work_from_home, enter_start_date, enter_end_date, select_reason, select_others, enter_wfh_reason, submit_wfh

ACTIONS = {
    "click_absence_management": click_absence_management,
    "click_absence_requests": click_absence_requests,
    "click_special_requests": click_special_requests,
    "click_apply": click_apply,
    "select_work_from_home": select_work_from_home,
    "enter_start_date": enter_start_date,
    "enter_end_date": enter_end_date,
    "select_reason": select_reason,
    "select_others": select_others,
    "enter_wfh_reason": enter_wfh_reason,
    "submit_wfh": submit_wfh,
}

STEP_ORDER = ['click_absence_management', 'click_absence_requests', 'click_special_requests', 'click_apply', 'select_work_from_home', 'enter_start_date', 'enter_end_date', 'select_reason', 'select_others', 'enter_wfh_reason', 'submit_wfh']
