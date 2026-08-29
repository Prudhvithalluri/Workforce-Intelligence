# OTP Debugging

## Backend console
Run the backend normally and look for:
- `OTP_REQUEST_ENTERED`
- `OTP_CHALLENGE_CREATED`
- `OTP_INTERRUPT_SENDING`
- `OTP_RESPONSE_DEBUG`
- `OTP_API_RESULT`
- `OTP_GRAPH_RESUME_STARTED`
- `OTP_SUBMIT_STARTED`

The OTP value itself is never logged.

## Browser console
Open DevTools -> Console and look for:
- `[API] request`
- `[API] response`
- `[AUTOMATION UI] action response`
- `[OTP UI] handleAutomationResult`
- `[OTP UI] opening OTP from status polling`
- `[OTP UI] OtpModal mounted`

The UI has a fallback: if the attendance POST does not contain the interrupt payload, the session-status polling endpoint can still detect the active `challenge_id` and open the OTP modal.

## Frontend
This package contains the source code. Install dependencies and run the normal Vite development command on your machine:
`npm install`
`npm run dev`

The existing `node_modules` and generated `dist` directory were intentionally excluded from this debug source package so they do not contain stale bundles.
