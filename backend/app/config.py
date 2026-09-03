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
    # AZURE OPENAI
    # =====================================================
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"

    # =====================================================
    # TARGET WEBSITE
    # =====================================================

    TARGET_SITE_URL: str = ""

    ATTENDANCE_SITE_ORIGIN: str = ""


    POST_LOGIN_BUTTON_SELECTOR: str = (
        'text="Continue"'
    )
        # =====================================================
    # EMAIL NOTIFICATIONS (Gmail SMTP)
    # =====================================================

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_TO_EMAIL: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_EMPLOYEE_NAME: str = ""
    SMTP_EMPLOYEE_PHONE: str = ""


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
    VIDEO_DIR: str = str(BASE_DIR / "session_recordings")
    VIDEO_WIDTH: int = 1280
    VIDEO_HEIGHT: int = 720

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

    WFH_WAIT_MS: int = 6000

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


    # =====================================================
    # VIDEO DIR PATH
    # =====================================================

    @property
    def video_dir_path(self) -> Path:

        logger.debug("resolving_video_dir configured=%s", bool(self.VIDEO_DIR))

        path = Path(
            self.VIDEO_DIR
        )

        if not path.is_absolute():

            path = BASE_DIR / path

        return path.resolve()

# =========================================================
# GLOBAL SETTINGS INSTANCE
# =========================================================

settings = Settings()