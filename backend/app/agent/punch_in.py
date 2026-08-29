"""Operation-specific target-site steps. Browser actions are implemented in common_steps.py."""
from agent.common_steps import click_punch_in, confirm_punch_in

ACTIONS = {
    "click_punch_in": click_punch_in,
    "confirm_punch_in": confirm_punch_in,
}

STEP_ORDER = ['click_punch_in', 'confirm_punch_in']
