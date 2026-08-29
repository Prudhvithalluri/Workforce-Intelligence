import json
import logging
from threading import Lock

from config import settings
from logging_utils import safe_id

logger = logging.getLogger(__name__)

_lock = Lock()


def _read() -> dict:
    logger.debug("user_store_read_started")
    path = settings.users_path
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(
            json.dumps({"users": []}, indent=2),
            encoding="utf-8",
        )
        logger.info("user_store_created")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid users.json: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("users.json must contain a JSON object")

    data.setdefault("users", [])
    logger.debug("user_store_read_finished user_count=%s", len(data["users"]))
    return data


def _write(data: dict) -> None:
    logger.debug("user_store_write_started user_count=%s", len(data.get("users", [])))
    settings.users_path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
    logger.info("user_store_write_finished")


def normalize_username(username: str) -> str:
    logger.debug("username_normalized user=%s", safe_id(username))
    return username.strip().lower()


def find_user(username: str) -> dict | None:
    logger.info("user_lookup_started user=%s", safe_id(username))
    normalized = normalize_username(username)

    with _lock:
        data = _read()
        for user in data.get("users", []):
            if normalize_username(str(user.get("username", ""))) == normalized:
                return user

    logger.info("user_lookup_finished user=%s found=%s", safe_id(username), False)
    return None


def register_user(username: str, target_password: str, app_pin: str) -> dict:
    logger.info("user_registration_started user=%s", safe_id(username))
    normalized = normalize_username(username)

    with _lock:
        data = _read()

        for user in data.get("users", []):
            if normalize_username(str(user.get("username", ""))) == normalized:
                raise ValueError("Username already exists")

        # DEMO ONLY: both target password and 4-digit app PIN are stored plainly.
        user = {
            "username": normalized,
            "target_password": target_password,
            "app_pin": app_pin,
        }

        data.setdefault("users", []).append(user)
        _write(data)

    return {"username": normalized}


def get_target_password(user: dict) -> str:
    logger.debug("target_password_lookup_started")
    password = user.get("target_password")
    if password is None or str(password) == "":
        raise ValueError("Target-site password is missing for this user")
    return str(password)


def verify_app_pin(username: str, app_pin: str) -> bool:
    logger.info("app_pin_verification_started user=%s", safe_id(username))
    user = find_user(username)
    if not user:
        logger.info("app_pin_verification_finished user=%s valid=%s", safe_id(username), False)
        return False
    valid = str(user.get("app_pin", "")) == str(app_pin)
    logger.info("app_pin_verification_finished user=%s valid=%s", safe_id(username), valid)
    return valid
