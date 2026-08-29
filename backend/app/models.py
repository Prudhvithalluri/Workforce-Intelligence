import logging
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
logger.debug("request_models_loaded")


class CheckUsernameRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=200,
    )


class RegisterRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=200,
    )

    target_password: str = Field(
        min_length=1,
        max_length=500,
    )

    app_pin: str = Field(
        pattern=r"^\d{4}$",
    )


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=200,
    )

    app_pin: str = Field(
        pattern=r"^\d{4}$",
    )


class OTPRequest(BaseModel):
    session_id: str = Field(
        min_length=1,
    )

    challenge_id: str = Field(
        min_length=1,
    )

    otp: str = Field(
        pattern=r"^\d{6}$",
    )


class Location(BaseModel):
    latitude: float = Field(
        ge=-90,
        le=90,
    )

    longitude: float = Field(
        ge=-180,
        le=180,
    )

    accuracy: Optional[float] = Field(
        default=None,
        ge=0,
    )

    captured_at: Optional[str] = None


class OperationRequest(BaseModel):
    """
    Used for Punch In and Punch Out.
    """

    session_id: str = Field(
        min_length=1,
    )

    location: Location


class WFHRequest(BaseModel):
    """
    Used for Work From Home.
    """

    session_id: str = Field(
        min_length=1,
    )

    start_date: str = Field(
        min_length=1,
        max_length=50,
    )

    end_date: str = Field(
        min_length=1,
        max_length=50,
    )

    reason: str = Field(
        min_length=1,
        max_length=2000,
    )

    location: Location