import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
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

    # Path of the saved screen recording for this session, populated once
    # the context is closed and Playwright finishes writing the video
    # file(s). If the main page and the Time & Attendance popup each
    # produced their own video (Playwright records one video per Page),
    # this is the MERGED single file when ffmpeg was available, or the
    # first of the individual parts otherwise -- see video_parts.
    video_path: str | None = None

    # If merging wasn't possible (ffmpeg not installed), this holds every
    # individual video file that was recorded for this session, in
    # chronological order, so nothing is silently lost.
    video_parts: list[str] | None = None

    # OTP state for the target site's human-in-the-loop verification.
    otp_challenge_id: str | None = None
    otp_target_site_url: str | None = None
    otp_attempt: int = 0

    target_authenticated: bool = False

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
# VIDEO MERGING
# ============================================================

async def _merge_video_parts(paths: list[str], session_id: str) -> str | None:
    """
    Playwright records one video per Page, not per BrowserContext. When
    the target site opens Time & Attendance in a popup, that popup is a
    new Page, so it gets its own separate video file -- splitting the
    recording right at that click.

    This stitches those separate files back into a single continuous
    video using ffmpeg's concat demuxer (stream copy, no re-encoding,
    since all parts share the same resolution/codec).

    Returns the merged file path, or None if ffmpeg isn't available or
    the merge failed for any reason -- callers should fall back to
    keeping the individual parts rather than losing them.
    """

    if len(paths) < 2:
        return paths[0] if paths else None

    ffmpeg_bin = shutil.which("ffmpeg")

    if not ffmpeg_bin:
        logger.warning(
            "ffmpeg_not_found_skipping_video_merge session=%s parts=%s",
            session_id[:8],
            len(paths),
        )
        return None

    output_dir = Path(paths[0]).parent
    output_path = output_dir / f"{session_id}_full.webm"
    list_file = output_dir / f"{session_id}_concat_list.txt"

    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for part_path in paths:
                # ffmpeg's concat demuxer resolves relative paths in this
                # list file relative to the list file's OWN directory, not
                # the process's working directory -- always write absolute
                # paths here to avoid any risk of doubled-up paths.
                absolute_path = str(Path(part_path).resolve())
                escaped = absolute_path.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        process = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(
                "ffmpeg_video_merge_failed session=%s returncode=%s stderr=%s",
                session_id[:8],
                process.returncode,
                stderr.decode(errors="ignore")[-2000:],
            )
            return None

        logger.info(
            "ffmpeg_video_merge_succeeded session=%s parts=%s output=%s",
            session_id[:8],
            len(paths),
            output_path,
        )

        return str(output_path)

    except Exception:
        logger.exception("ffmpeg_video_merge_error session=%s", session_id[:8])
        return None

    finally:
        try:
            list_file.unlink(missing_ok=True)
        except Exception:
            pass


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

            # Recording starts the moment this context is created. Video
            # size deliberately matches the viewport (VIDEO_WIDTH/HEIGHT):
            # in headed mode, Chromium can only actually render up to
            # whatever fits the real screen, so a video size larger than
            # the real screen pads the unrendered remainder with a solid
            # gray/black bar. VIDEO_WIDTH/HEIGHT default to 1280x720,
            # which fits virtually any real monitor.
            video_dir = settings.video_dir_path
            video_dir.mkdir(parents=True, exist_ok=True)

            viewport_size = {
                "width": settings.VIDEO_WIDTH,
                "height": settings.VIDEO_HEIGHT,
            }

            context = await browser.new_context(
                viewport=viewport_size,
                record_video_dir=str(video_dir),
                record_video_size=viewport_size,
            )

            page = await context.new_page()

            logger.info(
                "screen_recording_started session=%s video_dir=%s size=%sx%s",
                session_id[:8],
                video_dir,
                settings.VIDEO_WIDTH,
                settings.VIDEO_HEIGHT,
            )

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
            #
            # A video file is only finalized once its owning Page is
            # closed (which happens when the context closes), so grab
            # the Video handles BEFORE closing, then read .path() AFTER.
            #
            # Playwright records one video PER PAGE, not per context.
            # The Time & Attendance popup is a separate Page, so if it
            # was opened, it produced its own separate video file --
            # both are collected here and merged into one continuous
            # recording below.
            # ------------------------------------------------

            if session.context is not None:

                main_video = getattr(session.page, "video", None)

                attendance_video = None
                if (
                    session.attendance_page is not None
                    and session.attendance_page is not session.page
                ):
                    attendance_video = getattr(session.attendance_page, "video", None)

                try:
                    await session.context.close()
                except Exception:
                    pass

                video_paths: list[str] = []

                if main_video is not None:
                    try:
                        video_paths.append(await main_video.path())
                    except Exception:
                        logger.exception(
                            "screen_recording_save_failed session=%s page=main",
                            session_id[:8],
                        )

                if attendance_video is not None:
                    try:
                        video_paths.append(await attendance_video.path())
                    except Exception:
                        logger.exception(
                            "screen_recording_save_failed session=%s page=attendance",
                            session_id[:8],
                        )

                if len(video_paths) == 1:
                    session.video_path = video_paths[0]
                    session.video_parts = video_paths
                    logger.info(
                        "screen_recording_saved session=%s path=%s",
                        session_id[:8],
                        session.video_path,
                    )

                elif len(video_paths) > 1:
                    merged_path = await _merge_video_parts(video_paths, session_id)

                    if merged_path:
                        session.video_path = merged_path
                        session.video_parts = video_paths
                        logger.info(
                            "screen_recording_saved_merged session=%s path=%s parts=%s",
                            session_id[:8],
                            merged_path,
                            video_paths,
                        )
                    else:
                        # ffmpeg unavailable or merge failed -- keep both
                        # individual files rather than losing footage.
                        session.video_path = video_paths[0]
                        session.video_parts = video_paths
                        logger.warning(
                            "screen_recording_merge_unavailable session=%s parts=%s",
                            session_id[:8],
                            video_paths,
                        )

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