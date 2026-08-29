import operator
import logging
from typing import Annotated, Optional, TypedDict

logger = logging.getLogger(__name__)
logger.debug("agent_state_schema_loaded")


class AgentState(TypedDict, total=False):
    session_id: str
    username: str
    target_password: str
    operation: str

    current_step: str
    last_verified_step: str
    retry_count: int

    page_url: str
    page_title: str
    checks: dict

    action: Optional[str]
    action_result: Optional[str]
    error: Optional[str]
    recovery_reason: Optional[str]
    failed_action: Optional[str]
    failed_step: Optional[str]
    recovery_checks: dict
    force_inspect: bool

    otp_required: bool
    otp_challenge_id: Optional[str]
    otp: Optional[str]
    otp_target_site_url: Optional[str]
    post_otp_target_site_url: Optional[str]
    otp_verified: bool
    otp_invalid: bool
    otp_attempt: int

    start_date: Optional[str]
    end_date: Optional[str]
    reason: Optional[str]

    latitude: Optional[float]
    longitude: Optional[float]
    accuracy: Optional[float]
    captured_at: Optional[str]

    status: str
    result: Optional[dict]
    history: Annotated[list[dict], operator.add]
