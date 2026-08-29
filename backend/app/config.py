import logging
from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

logger = logging.getLogger(__name__)


# =========================================================
# BASE DIRECTORIES
# =========================================================

# backend/
BASE_DIR = Path(
    __file__
).resolve().parent.parent

ENV_FILE = BASE_DIR / ".env"

DEFAULT_USERS_FILE = (
    BASE_DIR
    / "data"
    / "users.json"
)


# =========================================================
# SETTINGS
# =========================================================

class Settings(BaseSettings):

    # =====================================================
    # AWS BEDROCK
    # =====================================================
    #
    # AWS credentials are loaded from backend/.env.
    #
    # AWS_SESSION_TOKEN is required when using temporary
    # AWS credentials. If your credentials are permanent,
    # it can remain empty.
    #
    # BEDROCK_MODEL_ID must be the model ID supported by
    # your AWS Bedrock account and region.
    #
    # Example:
    #
    # AWS_REGION=us-east-1
    # BEDROCK_MODEL_ID=your-model-id
    #
    # =====================================================

    AWS_ACCESS_KEY_ID: str = ""

    AWS_SECRET_ACCESS_KEY: str = ""

    AWS_SESSION_TOKEN: str = ""

    AWS_REGION: str = "us-east-1"

    BEDROCK_MODEL_ID: str = ""


    # =====================================================
    # TARGET WEBSITE
    # =====================================================

    TARGET_SITE_URL: str = ""

    ATTENDANCE_SITE_ORIGIN: str = ""


    # =====================================================
    # POST LOGIN
    # =====================================================
    #
    # After Sign In, the target website may show a button
    # that must be clicked before the OTP screen appears.
    #
    # Change this selector according to your target site.
    #
    # =====================================================

    POST_LOGIN_BUTTON_SELECTOR: str = (
        'text="Continue"'
    )


    # =====================================================
    # FRONTEND
    # =====================================================

    FRONTEND_ORIGIN: str = (
        "http://localhost:5173"
    )


    # =====================================================
    # USER JSON
    # =====================================================

    USERS_JSON_PATH: str = str(
        DEFAULT_USERS_FILE
    )


    # =====================================================
    # PLAYWRIGHT
    # =====================================================

    PLAYWRIGHT_HEADLESS: bool = False


    # =====================================================
    # AGENT RECOVERY
    # =====================================================

    MAX_AGENT_RETRIES: int = 3


    # =====================================================
    # BROWSER WAITS
    # =====================================================

    LOGIN_WAIT_MS: int = 3000

    POST_LOGIN_WAIT_MS: int = 5000

    ATTENDANCE_RENDER_WAIT_MS: int = 10000

    PUNCH_CONFIRM_WAIT_MS: int = 2000

    WFH_WAIT_MS: int = 3000

    ACTION_TIMEOUT_MS: int = 30000


    # =====================================================
    # PYDANTIC SETTINGS
    # =====================================================

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        extra="ignore",
    )


    # =====================================================
    # USERS FILE PATH
    # =====================================================

    @property
    def users_path(self) -> Path:

        logger.debug("resolving_users_path configured=%s", bool(self.USERS_JSON_PATH))

        path = Path(
            self.USERS_JSON_PATH
        )

        if not path.is_absolute():

            path = BASE_DIR / path

        return path.resolve()


# =========================================================
# GLOBAL SETTINGS INSTANCE
# =========================================================

settings = Settings()