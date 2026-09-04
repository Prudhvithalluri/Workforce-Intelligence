# InfoTIME Backend

## Run command

This project is arranged so the backend can be started exactly with:

```powershell
cd backend\app
.venv\Scripts\activate
uvicorn main:app --reload
```

The API is then available at `http://127.0.0.1:8000`.

Swagger: `http://127.0.0.1:8000/docs`

Health: `http://127.0.0.1:8000/health`

## Setup

From `backend`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

Create `.env` from `.env.example` and set at least:

```env
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4.1-mini
TARGET_SITE_URL=https://your-target-site.example/login
POST_LOGIN_BUTTON_SELECTOR=text="Continue"
FRONTEND_ORIGIN=http://localhost:5173
```

## Flow

1. Frontend sends username.
2. Backend checks `data/users.json`.
3. Existing user: frontend asks for the 4-digit app PIN.
4. New user: frontend sends target-site username/password and a new 4-digit app PIN to `/api/auth/register`.
5. Login starts one Playwright browser session.
6. The LLM chooses predefined browser actions one at a time.
7. After target-site sign-in, the predefined post-login button is clicked.
8. The target site shows OTP. LangGraph interrupts and the frontend asks the user for OTP.
9. `/api/auth/verify-otp` resumes the same LangGraph/browser session.
10. After login, the user can Punch In, Punch Out, or WFH.
11. Punch In/Out capture browser location in the frontend and send it to the backend.
12. The backend applies that location to the Playwright context before attendance actions.
13. Every browser step is verified using deterministic selectors/state.
14. If a step fails, LangGraph returns to `last_verified_step`, re-inspects the page, and lets the LLM choose the next predefined action from that verified point.

## Demo credential storage

For this demo, `data/users.json` stores `target_password` and `app_pin` as plain text. Do not use this storage design for production.

## Selector changes

Edit `app/browser/helpers.py` for the target-site selectors. The post-login button is configurable in `.env` through `POST_LOGIN_BUTTON_SELECTOR`.
