const API =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    const error = new Error(
      body.detail ||
        body.message ||
        body.error ||
        "Request failed"
    );
    error.status = response.status;
    throw error;
  }

  return body;
}

export const api = {
  // ============================================================
  // AUTHENTICATION
  // ============================================================

  /**
   * Check whether the application username exists.
   *
   * Existing user:
   *   -> frontend asks for the 4-digit application PIN.
   *
   * New user:
   *   -> frontend shows registration.
   */
  checkUsername(username) {
    return request("/api/auth/check-username", {
      method: "POST",
      body: JSON.stringify({
        username: username.trim(),
      }),
    });
  },

  /**
   * Register a new application user.
   *
   * target_password:
   *   Password used by the target attendance website.
   *
   * app_pin:
   *   4-digit PIN used for this application.
   */
  register(username, target_password, app_pin) {
    return request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: username.trim(),
        target_password,
        app_pin,
      }),
    });
  },

  /**
   * Application login.
   *
   * IMPORTANT:
   *
   * This endpoint should ONLY:
   *
   *   1. Find the username in users.json
   *   2. Verify the 4-digit application PIN
   *   3. Create/return an application session ID
   *
   * It should NOT start Playwright.
   * It should NOT open the target website.
   * It should NOT start the LLM workflow.
   *
   * Browser automation starts only after the user clicks
   * Punch In / Punch Out / Work From Home on the dashboard.
   */
  login(username, pin) {
    return request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: username.trim(),
        app_pin: String(pin).trim(),
      }),
    });
  },

  /**
   * Submit OTP entered by the user.
   *
   * The OTP comes from the target website.
   * The user enters it in the frontend.
   */
  verifyOtp(session_id, challenge_id, otp) {
    return request("/api/auth/verify-otp", {
      method: "POST",
      body: JSON.stringify({
        session_id,
        challenge_id,
        otp: String(otp).trim(),
      }),
    });
  },

  // ============================================================
  // ATTENDANCE
  // ============================================================

  /**
   * Punch In.
   *
   * IMPORTANT:
   * This is where browser automation should start if it has
   * not already been started.
   *
   * Frontend gets the user's current location and sends it
   * to the backend.
   */
  punchIn(session_id, location) {
    return request("/api/attendance/punch-in", {
      method: "POST",
      body: JSON.stringify({
        session_id,
        location,
      }),
    });
  },

  /**
   * Punch Out.
   *
   * Browser automation is started/reused by the backend here.
   */
  punchOut(session_id, location) {
    return request("/api/attendance/punch-out", {
      method: "POST",
      body: JSON.stringify({
        session_id,
        location,
      }),
    });
  },

  /**
   * Work From Home.
   *
   * Example payload:
   *
   * {
   *   session_id,
   *   location,
   *   reason,
   *   date
   * }
   */
  wfh(payload) {
    return request("/api/attendance/wfh", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // ============================================================
  // SESSION / AUTOMATION STATUS
  // ============================================================

  /**
   * Get the current application/automation session status.
   *
   * This is useful for displaying:
   *
   *   Opening website...
   *   Entering username...
   *   Entering password...
   *   Waiting for OTP...
   *   Opening Time & Attendance...
   *   Clicking Punch In...
   *   Confirming Punch In...
   */
  getSessionStatus(session_id) {
    return request(
      `/api/auth/session/${encodeURIComponent(session_id)}`,
      {
        method: "GET",
      }
    );
  },

  /**
   * Cancel an active automation workflow.
   */
  cancelSession(session_id) {
    return request(
      `/api/auth/session/${encodeURIComponent(session_id)}/cancel`,
      {
        method: "POST",
      }
    );
  },

  // ============================================================
  // OPTIONAL: HEALTH CHECK
  // ============================================================

  /**
   * Simple backend health check.
   *
   * Only use this if your backend exposes /health.
   */
  health() {
    return request("/health", {
      method: "GET",
    });
  },
};