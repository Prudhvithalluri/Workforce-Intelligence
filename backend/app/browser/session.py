import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse
from uuid import uuid4

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from config import settings

logger = logging.getLogger(__name__)


# ============================================================
# BROWSER SESSION
# ============================================================

@dataclass
class BrowserSession:
    session_id: str

    # ========================================================
    # APPLICATION USER
    # ========================================================

    username: str | None = None

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    playwright: object | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None

    # ========================================================
    # ATTENDANCE
    # ========================================================

    attendance_page: Page | None = None
    location: dict | None = None

    # OTP state for the target site's human-in-the-loop verification.
    otp_challenge_id: str | None = None
    otp_target_site_url: str | None = None
    otp_attempt: int = 0

    # ========================================================
    # TARGET-SITE AUTHENTICATION
    # ========================================================
    #
    # True only after the target site's OTP has been verified
    # (i.e. submit_otp confirmed the /dashboard URL) for the
    # CURRENT browser page/context.
    #
    # This lets subsequent Punch In / Punch Out / WFH operations
    # skip the entire open_site -> username -> password -> OTP
    # sequence and resume directly from "authenticated", so the
    # user is only asked for OTP ONCE per browser session.
    #
    # It is reset to False whenever the underlying Playwright
    # page is (re)created, since a new page means the target
    # site is no longer logged in.
    # ========================================================

    target_authenticated: bool = False

    # ========================================================
    # WORKFLOW
    # ========================================================

    workflow: dict = field(
        default_factory=lambda: {
            "status": "idle",
            "current_step": "",
            "last_verified_step": "",
            "message": "",
            "error": None,
            "operation": None,
            "retry_count": 0,
            "browser_started": False,
        }
    )

    # ========================================================
    # OPERATION LOCK
    # ========================================================

    operation_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock
    )

    # ========================================================
    # LOCATION
    # ========================================================

    async def apply_location(
        self,
        location: dict,
        page: Page | None = None,
    ) -> None:

        logger.info("location_application_started session=%s", self.session_id[:8])

        if self.context is None:
            raise RuntimeError(
                "Browser context is not available"
            )

        latitude = float(
            location["latitude"]
        )

        longitude = float(
            location["longitude"]
        )

        accuracy = float(
            location.get("accuracy") or 50
        )

        if not -90 <= latitude <= 90:
            raise ValueError(
                "Invalid latitude"
            )

        if not -180 <= longitude <= 180:
            raise ValueError(
                "Invalid longitude"
            )

        geolocation = {
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
        }

        await self.context.set_geolocation(
            geolocation
        )

        self.location = {
            **location,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
        }

        # ====================================================
        # TARGET ORIGINS
        # ====================================================

        origins = set()

        for raw in [
            settings.TARGET_SITE_URL,
            settings.ATTENDANCE_SITE_ORIGIN,
        ]:

            if raw:

                parsed = urlparse(raw)

                if parsed.scheme and parsed.netloc:

                    origins.add(
                        f"{parsed.scheme}://{parsed.netloc}"
                    )

        # ====================================================
        # CURRENT PAGE ORIGIN
        # ====================================================

        if page is not None and page.url:

            parsed = urlparse(page.url)

            if parsed.scheme and parsed.netloc:

                origins.add(
                    f"{parsed.scheme}://{parsed.netloc}"
                )

        # ====================================================
        # GEOLOCATION PERMISSIONS
        # ====================================================

        for origin in origins:

            try:

                await self.context.grant_permissions(
                    ["geolocation"],
                    origin=origin,
                )

            except Exception:
                logger.warning("geolocation_permission_failed origin_host=%s", urlparse(origin).netloc)

        # ====================================================
        # ACTIVE PAGE ORIGIN
        # ====================================================

        if page is not None:

            parsed = urlparse(page.url)

            if parsed.scheme and parsed.netloc:

                await self.context.grant_permissions(
                    ["geolocation"],
                    origin=(
                        f"{parsed.scheme}://"
                        f"{parsed.netloc}"
                    ),
                )

            logger.info("location_application_finished session=%s origins=%s", self.session_id[:8], len(origins))
        # ========================================================
    # ACTIVE PAGE
    # ========================================================

    def active_page(self) -> Page:
        """
        Return the active Playwright page used by the automation.

        Prefer attendance_page when it exists.
        Otherwise use the main page.
        """

        if self.attendance_page is not None:
            if not self.attendance_page.is_closed():
                return self.attendance_page

        if self.page is not None:
            if not self.page.is_closed():
                return self.page

        raise RuntimeError(
            "No active browser page is available. "
            "The browser has not been started."
        )

# ============================================================
# SESSION MANAGER
# ============================================================

class BrowserSessionManager:

    def __init__(self):

        self._sessions: dict[
            str,
            BrowserSession,
        ] = {}

        self._lock = asyncio.Lock()

    # ========================================================
    # CREATE APPLICATION SESSION
    # ========================================================
    #
    # IMPORTANT:
    #
    # THIS DOES NOT START PLAYWRIGHT.
    #
    # Login with the application PIN only creates this
    # lightweight session.
    #
    # Browser starts later when Punch In / Punch Out / WFH
    # calls start_browser().
    # ========================================================

    async def create(self) -> BrowserSession:

        async with self._lock:

            session = BrowserSession(
                session_id=str(uuid4())
            )

            self._sessions[
                session.session_id
            ] = session

            logger.info("browser_session_created session=%s", session.session_id[:8])

            return session

    # ========================================================
    # START BROWSER
    # ========================================================

    async def start_browser(
        self,
        session_id: str,
    ) -> BrowserSession:

        session = self.get(session_id)

        logger.info("browser_start_requested session=%s", session_id[:8])

        # ----------------------------------------------------
        # Don't start twice
        # ----------------------------------------------------

        if (
            session.playwright is not None
            and session.browser is not None
            and session.context is not None
            and session.page is not None
            and not session.page.is_closed()
        ):
            logger.info("browser_reused session=%s", session_id[:8])
            return session

        if session.page is not None and session.page.is_closed():
            logger.warning("browser_page_closed_recreating session=%s", session_id[:8])
            session.page = None
            session.attendance_page = None
            session.context = None
            session.browser = None
            session.playwright = None
            # A fresh page means the target site is no longer logged in.
            session.target_authenticated = False

        # ----------------------------------------------------
        # Start Playwright
        # ----------------------------------------------------

        pw = await async_playwright().start()

        try:

            browser = await pw.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS
            )

            context = await browser.new_context(
                viewport={
                    "width": 1920,
                    "height": 1080,
                }
            )

            page = await context.new_page()

        except Exception:
            logger.exception("browser_start_failed session=%s", session_id[:8])

            try:
                await pw.stop()
            except Exception:
                pass

            raise

        # ----------------------------------------------------
        # Save Playwright objects
        # ----------------------------------------------------

        session.playwright = pw
        session.browser = browser
        session.context = context
        session.page = page

        session.workflow.update(
            {
                "browser_started": True,
            }
        )

        logger.info("browser_started session=%s headless=%s", session_id[:8], settings.PLAYWRIGHT_HEADLESS)

        return session

    # ========================================================
    # GET SESSION
    # ========================================================

    def get(
        self,
        session_id: str,
    ) -> BrowserSession:

        session = self._sessions.get(
            session_id
        )

        if not session:

            raise KeyError(
                "Browser session not found or expired"
            )

        logger.debug("browser_session_retrieved session=%s", session_id[:8])

        return session

    # ========================================================
    # CLOSE SESSION
    # ========================================================

    async def close(
        self,
        session_id: str,
    ) -> None:

        async with self._lock:

            session = self._sessions.pop(
                session_id,
                None,
            )

            if not session:
                logger.info("browser_close_skipped session=%s reason=missing", session_id[:8])
                return

            # ------------------------------------------------
            # Close context
            # ------------------------------------------------

            if session.context is not None:

                try:
                    await session.context.close()
                except Exception:
                    pass

                session.context = None

            # ------------------------------------------------
            # Close browser
            # ------------------------------------------------

            if session.browser is not None:

                try:
                    await session.browser.close()
                except Exception:
                    pass

                session.browser = None

            # ------------------------------------------------
            # Stop Playwright
            # ------------------------------------------------

            if session.playwright is not None:

                try:
                    await session.playwright.stop()
                except Exception:
                    pass

                session.playwright = None

            session.page = None
            session.attendance_page = None

            session.workflow.update(
                {
                    "browser_started": False,
                }
            )
            logger.info("browser_session_closed session=%s", session_id[:8])


# ============================================================
# GLOBAL SESSION MANAGER
# ============================================================

session_manager = BrowserSessionManager()
