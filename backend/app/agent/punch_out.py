"""Operation-specific target-site steps. Browser actions are implemented in common_steps.py."""
from agent.common_steps import click_punch_out, confirm_punch_out

ACTIONS = {
    "click_punch_out": click_punch_out,
    "confirm_punch_out": confirm_punch_out,
}

STEP_ORDER = ['click_punch_out', 'confirm_punch_out']
