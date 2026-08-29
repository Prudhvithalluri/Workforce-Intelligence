# Completed backend changes

Based on the uploaded backend source and the target-site working steps already present in the project.

## Main fixes

### 1. LLM action constraint
`app/agent/llm.py`
- Bedrock remains the decision-maker.
- Python remains the hard safety boundary.
- If Bedrock returns an action that is not in the current legal action list and there is exactly one legal action, Python rejects the model action and uses that only legal action.
- This fixes the observed `app_authenticated -> available ['open_site']` / `LLM selected click_punch_in` failure without allowing an invalid action to execute.

### 2. Defined workflow
`app/agent/nodes.py` and `app/agent/prompts.py`
- Application authentication ends at `app_authenticated`.
- Attendance starts the target-site browser.
- The common target-site flow remains: open site -> username -> next -> password -> sign in -> email -> OTP -> dashboard -> Me -> Time & Attendance.
- Operation-specific actions are selected only after `time_attendance_clicked`.
- Punch In, Punch Out and WFH registries remain separate modules importing common browser functions.

### 3. OTP
`app/agent/common_steps.py`, `app/agent/state.py`, `app/routers/auth.py`, `app/routers/attendance.py`
- The URL used is the Playwright TARGET SITE URL.
- The URL before OTP Submit is captured.
- OTP is accepted only when the target-site URL reaches `/dashboard`.
- A different URL is not considered successful.
- If `/dashboard` is not reached, the same OTP challenge remains available and the frontend receives `otp_required=true`, `otp_invalid=true`.
- Successful OTP returns `otp_verified=true`.

### 4. Navigation
`app/agent/common_steps.py`
- Existing `NAV_SELECTORS["me"]` (`div.label`) is retained.
- Exact text matching is case-insensitive.
- A bounded `get_by_text(..., exact=True)` fallback is used when the target site renders the label differently.

### 5. Location
- Latitude/longitude/accuracy remain backend state supplied by the frontend.
- Location is never sent to Bedrock.
- Location is applied by Python immediately before the relevant Punch In, Punch Out or WFH action.

### 6. Recovery
- Existing recovery mechanism is retained.
- After a Playwright error, the expected state of the failed step is checked before rewinding.
- Invalid LLM actions are never executed.

### 7. Service bug
`app/services/agent_service.py`
- Fixed the `start_target_login()` path so it obtains its LangGraph checkpoint with `graph.get_state(...)` before reading `checkpoint.values`.

## Files not changed
- `app/agent/punch_in.py`
- `app/agent/punch_out.py`
- `app/agent/wfh.py`
- `app/browser/helpers.py`
- `app/browser/session.py`
- `app/config.py`
- `app/main.py`
- `app/models.py`
- `app/services/user_store.py`

## Security
The original `.env` and `data/users.json` were NOT packaged because they contain credentials/passwords/PINs. Use the original files locally. Safe examples are included as `.env.example` and `data/users.json.example`.

## Validation
- All Python source files AST parsed successfully.
- `python -m compileall -q app` completed successfully.
- Action names referenced by the workflow were checked against the current action definitions/registries.
