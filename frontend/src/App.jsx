import React, { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Bell,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Fingerprint,
  House,
  LogOut,
  Menu,
  ShieldCheck,
  UserRound,
  X,
  AlertCircle,
  Loader2,
} from "lucide-react";

import { api } from "./api";

const EMPTY_PIN = ["", "", "", ""];

// Turns backend-style codes like "punch_in_confirmed" or
// "target_site_opened" into readable text like "Punch in confirmed".
function humanize(text) {
  if (!text || typeof text !== "string") return text;
  const words = text.replace(/[_-]+/g, " ").trim();
  if (!words) return words;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function getCurrentLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Browser geolocation is not available."));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          captured_at: new Date().toISOString(),
        });
      },
      (error) => {
        if (error.code === 1) {
          reject(
            new Error(
              "Location permission was denied. Please allow location access."
            )
          );
        } else if (error.code === 2) {
          reject(new Error("Your current location could not be determined."));
        } else {
          reject(new Error("Timed out while getting your current location."));
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0,
      }
    );
  });
}

function PinInput({ value, onChange, label = "Enter 4-Digit PIN", onEnter }) {
  const pinValue = Array.isArray(value) ? value.join("") : String(value || "");

  const handleChange = (event) => {
    const digits = event.target.value.replace(/\D/g, "").slice(0, 4);
    onChange([
      digits[0] || "",
      digits[1] || "",
      digits[2] || "",
      digits[3] || "",
    ]);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && onEnter) {
      event.preventDefault();
      onEnter();
    }
  };

  return (
    <div className="pin-screen">
      <h1>{label}</h1>
      <p>Enter your PIN to access home</p>

      <input
        className="text-input pin-input"
        type="password"
        inputMode="numeric"
        pattern="[0-9]*"
        autoComplete="one-time-code"
        maxLength={4}
        autoFocus
        value={pinValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="4-digit PIN"
        aria-label={label}
      />

      <div className="pin-hint">
        Use your keyboard. Press Enter to continue.
      </div>
    </div>
  );
}
function OtpModal({ onSubmit, onCancel, busy, error, progressStep, progressMessage }) {
  const [otp, setOtp] = useState("");

  return (
    <div className="modal-backdrop">
      <div className="modal-card otp-card">
        {onCancel && (
          <button
            className="modal-close"
            onClick={onCancel}
            disabled={busy}
            title="Cancel and start over"
          >
            <X size={20} />
          </button>
        )}

        <div className="modal-icon">
          <ShieldCheck size={28} />
        </div>

        <h2>Verify OTP</h2>

        <p>
          The target website is requesting an OTP. Enter the OTP you received
          to continue.
        </p>

        <label>ENTER OTP</label>

        <input
          className="text-input otp-input"
          inputMode="numeric"
          autoFocus
          maxLength={6}
          value={otp}
          onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && otp.length === 6 && !busy) {
              e.preventDefault();
              onSubmit(otp);
            }
          }}
          placeholder="Enter 6-digit OTP"
        />

        {error && <div className="error">{error}</div>}

        <button
          className="primary-button"
          disabled={otp.length !== 6 || busy}
          onClick={() => otp.length === 6 && onSubmit(otp)}
        >
          {busy ? "Verifying & continuing..." : "Verify OTP"}
        </button>

        {busy && (
          <>
            {/* Live progress from the backend while the whole operation
                (login -> click_me -> time_attendance -> punch in/out ->
                confirm) keeps running after OTP is accepted. Without this
                the modal looked frozen for 30-60+ seconds. */}
            <div className="otp-progress">
              <Loader2 size={16} className="spin" />
              <span>{humanize(progressMessage) || "Continuing automation..."}</span>
            </div>
            <p className="pin-hint">
              This is only needed once per session — hang tight while we
              finish the request.
            </p>
          </>
        )}

        {!busy && onCancel && (
          <button className="link-button" onClick={onCancel}>
            Didn't get an OTP? Cancel and start over
          </button>
        )}
      </div>
    </div>
  );
}

function LiveUpdates({ status, step, message, error }) {
  const completed = status === "completed" || status === "success";
  const failed = status === "failed" || status === "error";
  const waiting = status === "waiting_for_user" || status === "waiting";
  const running =
    status === "running" || status === "in_progress" || status === "recovering";

  const statusClass = completed
    ? "status-completed"
    : failed
    ? "status-failed"
    : waiting
    ? "status-waiting"
    : running
    ? "status-running"
    : "";

  const statusLabel = completed
    ? "Completed"
    : failed
    ? "Failed"
    : waiting
    ? "Waiting for OTP"
    : running
    ? "In progress"
    : "Idle";

  const nothingYet = !status && !step && !message && !error;

  return (
    <div className="live-updates-grid">
      <div className={`update-card ${statusClass}`}>
        <span className="update-label">Status</span>
        <span className="update-value">
          {completed && <CheckCircle2 size={16} />}
          {failed && <AlertCircle size={16} />}
          {(running || waiting) && <Loader2 size={16} className="spin" />}
          {!completed && !failed && !running && !waiting && (
            <Clock3 size={16} />
          )}
          {statusLabel}
        </span>
      </div>

      <div className="update-card">
        <span className="update-label">Current step</span>
        <span className="update-value">{step || "—"}</span>
      </div>

      <div className={`update-card update-card-wide ${error ? "status-failed" : ""}`}>
        <span className="update-label">{error ? "Error" : "Message"}</span>
        <span className="update-value">
          {error && <AlertCircle size={16} />}
          {error || message || (nothingYet ? "No activity yet." : "—")}
        </span>
      </div>
    </div>
  );
}

function StepsLog({ steps }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [steps.length]);

  if (!steps.length) {
    return (
      <div className="steps-log steps-log-empty">
        No steps yet. They'll appear here as an action runs.
      </div>
    );
  }

  return (
    <div className="steps-log">
      {steps.map((entry, index) => (
        <div className="steps-log-row" key={entry.id}>
          <span className="steps-log-index">{index + 1}</span>
          <span className="steps-log-text">{entry.text}</span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function WfhModal({ sessionId, onClose, onSuccess }) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [locationStatus, setLocationStatus] = useState(
    "Location will be captured on submit"
  );

  // A synchronous guard against double-submission. `disabled={busy}` on the
  // button only takes effect after React re-renders, which happens
  // asynchronously -- two rapid clicks (double-click, or an accidental
  // double-tap on mobile) can both fire submit() before that re-render
  // happens, sending two concurrent WFH requests for the same session.
  // The backend serializes them, but the second response can still end up
  // overwriting the first one's OTP challenge in the Dashboard, leaving
  // neither modal in a consistent, visible state. A ref updates instantly,
  // with no render delay, so this closes the gap completely.
  const submittingRef = useRef(false);

  const submit = async () => {
    if (submittingRef.current) return;

    setError("");

    if (!startDate || !endDate || !reason.trim()) {
      setError("Start date, end date and reason are required.");
      return;
    }

    if (new Date(endDate) < new Date(startDate)) {
      setError("End date cannot be before start date.");
      return;
    }

    submittingRef.current = true;
    setBusy(true);

    try {
      setLocationStatus("Requesting your current location...");
      const location = await getCurrentLocation();

      setLocationStatus(
        `Location captured • ±${Math.round(location.accuracy || 0)}m`
      );

      const toTargetDate = (iso) => {
        const [y, m, d] = iso.split("-");
        return `${d}/${m}/${y}`;
      };

      const result = await api.wfh({
        session_id: sessionId,
        start_date: toTargetDate(startDate),
        end_date: toTargetDate(endDate),
        reason: reason.trim(),
        location,
      });

      const resultStatus = result?.status || result?.details?.status;
      const requestFailed = resultStatus === "failed" || resultStatus === "error";

      if (requestFailed) {
        // The backend ran the automation and it genuinely failed (e.g. a
        // selector timeout on the target site). This comes back as a
        // normal response, not a thrown error, so it must be checked
        // explicitly. Keep this form open with everything the user typed
        // still in place, and show the failure right here instead of
        // silently dismissing to the dashboard and losing their input.
        setError(
          result?.message ||
            result?.details?.message ||
            "WFH request failed. Please try again."
        );
        setLocationStatus("Location captured, but the request failed.");
        return;
      }

      onSuccess(result);
    } catch (e) {
      setError(e.message);
      setLocationStatus("Location not captured");
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card wfh-card">
        <button
          className="modal-close"
          onClick={onClose}
          disabled={busy}
        >
          <X size={20} />
        </button>

        <h2>Apply Special Request</h2>

        <div className="tabs">
          <button className="active">Apply Days</button>
          <button disabled>Apply Hourly</button>
        </div>

        <div className="wfh-form">
          <div>
            <label>SELECT TYPE*</label>
            <div className="fake-select">Work From Home</div>
          </div>

          <div>
            <label>START DATE*</label>
            <input
              className="text-input"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div>
            <label>END DATE*</label>
            <input
              className="text-input"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div>
            <label>REASON</label>
            <div className="fake-select">Others</div>
          </div>

          <div>
            <label>ENTER REASON*</label>
            <textarea
              className="text-input"
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Enter your reason"
            />
          </div>
        </div>

        <div className="location-status">
          <House size={18} />
          {locationStatus}
        </div>

        {error && <div className="error">{error}</div>}

        <div className="modal-actions">
          <button
            className="secondary-button"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>

          <button
            className="primary-button"
            disabled={busy}
            onClick={submit}
          >
            {busy ? "Submitting..." : "Submit Request"}
          </button>
        </div>
      </div>
    </div>
  );
}

function LoginPage({ onAuthenticated }) {
  const [username, setUsername] = useState("");
  const [targetPassword, setTargetPassword] = useState("");
  const [pin, setPin] = useState([...EMPTY_PIN]);
  const [step, setStep] = useState("username");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [challengeId, setChallengeId] = useState(null);

  const checkUsername = async () => {
    setError("");

    if (!username.trim()) {
      setError("Enter your username.");
      return;
    }

    setBusy(true);

    try {
      const result = await api.checkUsername(username.trim());

      if (result.exists) {
        setPin([...EMPTY_PIN]);
        setStep("pin");
      } else {
        setStep("register-password");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const register = async () => {
    setError("");

    const pinString = pin.join("");

    if (!targetPassword) {
      setError("Enter the target-site password.");
      return;
    }

    if (!/^\d{4}$/.test(pinString)) {
      setError("Create a 4-digit PIN.");
      return;
    }

    setBusy(true);

    try {
      const result = await api.register(
        username.trim(),
        targetPassword,
        pinString
      );

      setTargetPassword("");
      setPin([...EMPTY_PIN]);

      if (result.status === "otp_required" || result.requires_otp === true) {
        setSessionId(result.session_id);
        setChallengeId(result.challenge_id);
        setStep("otp");
      } else {
        setStep("pin");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const login = async () => {
    setError("");

    const pinString = pin.join("");

    if (!/^\d{4}$/.test(pinString)) {
      setError("Enter your 4-digit PIN.");
      return;
    }

    setBusy(true);

    try {
      const result = await api.login(username.trim(), pinString);

      if (!result.session_id) {
        throw new Error("Backend did not return a session ID.");
      }

      setSessionId(result.session_id);

      const loggedInUsername =
        result.username || username.trim().toLowerCase();

      localStorage.setItem("InfoTIME_username", loggedInUsername);

      if (
        result.status === "otp_required" ||
        result.requires_otp === true
      ) {
        setChallengeId(result.challenge_id);
        setStep("otp");
      } else {
        onAuthenticated(result.session_id, loggedInUsername);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const verifyOtp = async (otp) => {
    const cleanOtp = String(otp || "").replace(/\D/g, "").slice(0, 6);

    if (!sessionId) {
      setError("Automation session is missing.");
      return;
    }

    if (!challengeId) {
      setError("OTP challenge is missing.");
      return;
    }

    if (!/^\d{6}$/.test(cleanOtp)) {
      setError("Enter a valid 6-digit OTP.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      const result = await api.verifyOtp(sessionId, challengeId, cleanOtp);

      if (
        result.status === "otp_required" ||
        result.requires_otp === true
      ) {
        setChallengeId(result.challenge_id);
        setError("A new OTP was requested. Please enter it.");
        return;
      }

      if (
        result.status === "completed" ||
        result.status === "running" ||
        result.status === "authenticated" ||
        result.success === true
      ) {
        onAuthenticated(
          sessionId,
          username.trim().toLowerCase()
        );
      } else {
        setError(result.message || "OTP verification failed.");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (step === "otp") {
    return (
      <OtpModal
        onSubmit={verifyOtp}
        onCancel={async () => {
          if (sessionId) {
            try {
              await api.cancelSession(sessionId);
            } catch (e) {
              // Best-effort: still reset the local UI even if the backend
              // call fails (e.g. session already gone).
            }
          }
          setChallengeId(null);
          setError("");
          setStep("username");
        }}
        busy={busy}
        error={error}
      />
    );
  }

  if (step === "pin") {
    return (
      <main className="auth-shell">
        <div className="brand-block">
          <div className="logo-mark">
            <House size={32} />
          </div>
          <h1>InfoTIME</h1>
          <p>Enterprise Attendance Suite</p>
        </div>

        <PinInput
          value={pin}
          onChange={setPin}
          onEnter={login}
          label="Enter 4-Digit PIN"
        />

        {error && <div className="error center">{error}</div>}

        <button
          className="primary-button auth-submit"
          disabled={busy}
          onClick={login}
        >
          {busy ? "Signing In..." : "Continue"}
        </button>

        <div className="biometric">
          <Fingerprint size={24} />
          Use Biometric Fingerprint
        </div>
      </main>
    );
  }

  return (
    <main className="auth-shell">
      <div className="brand-block">
        <div className="logo-mark">
          <House size={32} />
        </div>
        <h1>InfoTIME</h1>
        <p>Enterprise Attendance Suite</p>
      </div>

      <div className="form-stack">
        <label>TARGET SITE USERNAME</label>

        <input
          className="text-input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !busy) {
              e.preventDefault();
              checkUsername();
            }
          }}
          placeholder="Enter target site username"
          disabled={step === "register-password"}
          autoFocus
        />

        {step === "username" && (
          <button
            className="primary-button"
            disabled={busy}
            onClick={checkUsername}
          >
            {busy ? "Checking..." : "Continue"}
          </button>
        )}

        {step === "register-password" && (
          <>
            <label>TARGET SITE PASSWORD</label>

            <input
              className="text-input"
              type="password"
              value={targetPassword}
              onChange={(e) => setTargetPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !busy) {
                  e.preventDefault();
                  register();
                }
              }}
              placeholder="Password for target site"
              autoFocus
            />

            <label>CREATE 4-DIGIT APP PIN</label>

            <PinInput
              value={pin}
              onChange={setPin}
              onEnter={register}
              label="Create 4-Digit PIN"
            />

            <button
              className="primary-button"
              disabled={busy}
              onClick={register}
            >
              {busy ? "Registering..." : "Register"}
            </button>

            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => {
                setTargetPassword("");
                setPin([...EMPTY_PIN]);
                setError("");
                setStep("username");
              }}
            >
              Back
            </button>
          </>
        )}
      </div>

      {error && <div className="error center">{error}</div>}
    </main>
  );
}

function Dashboard({ sessionId, username, onLogout }) {
  const [wfhOpen, setWfhOpen] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  // Same synchronous double-click guard as WfhModal's submittingRef --
  // `disabled={Boolean(busyAction)}` only takes effect after a re-render,
  // so a rapid double-click/double-tap could otherwise fire two concurrent
  // Punch In/Out requests before React disables the button.
  const actionInFlightRef = useRef(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [automationStatus, setAutomationStatus] = useState(null);
  const [automationStep, setAutomationStep] = useState("");
  const [automationMessage, setAutomationMessage] = useState("");
  const [otpChallengeId, setOtpChallengeId] = useState(null);
  const [otpAction, setOtpAction] = useState("");
  const [otpBusy, setOtpBusy] = useState(false);
  const [otpError, setOtpError] = useState("");

  const otpVerificationActiveRef = useRef(false);
  // Running log of every step the backend has reported for this dashboard
  // session (login/OTP, punch in/out, WFH, ...). This is intentionally
  // never cleared between actions -- it keeps accumulating so the user can
  // scroll back through everything that happened this session -- and is
  // only erased on logout (see logout() below).
  const [stepsLog, setStepsLog] = useState([]);
  const stepsLogIdRef = useRef(0);

  const logStep = (text) => {
    if (!text) return;
    setStepsLog((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.text === text) return prev; // de-dupe consecutive repeats
      stepsLogIdRef.current += 1;
      return [...prev, { id: stepsLogIdRef.current, text }];
    });
  };

  // Any time the live step/message changes, append it to the persistent
  // steps log. Centralizing this here (instead of calling logStep at every
  // call site that sets automationStep/automationMessage) guarantees the
  // log always matches what LiveUpdates is showing.
  useEffect(() => {
    if (!automationStep && !automationMessage) return;
    const text = automationStep && automationMessage
      ? `${humanize(automationStep)}: ${automationMessage}`
      : humanize(automationStep) || automationMessage;
    logStep(text);
  }, [automationStep, automationMessage]);

  // The background poller (below) reads this to avoid redundantly
  // re-triggering the OTP modal for a challenge that's already open/being
  // verified. Using a ref instead of the state directly keeps poll()'s
  // closure fresh without needing to restart the polling interval every
  // time otpChallengeId changes.
  const otpChallengeIdRef = useRef(null);
  useEffect(() => {
    otpChallengeIdRef.current = otpChallengeId;
  }, [otpChallengeId]);

  const processAutomationResult = (result, actionName, { otpJustVerified = false } = {}) => {
    const status =
      result?.status ||
      result?.details?.status ||
      "completed";

    const step =
      result?.step ||
      result?.current_step ||
      result?.details?.step ||
      "";

    let backendMessage = humanize(
      result?.message ||
        result?.details?.message ||
        result?.details?.status ||
        `${actionName} completed`
    );

    // The OTP challenge is only ever solved once per browser session. When
    // this result is the direct continuation of an OTP submission, make
    // that success explicit before showing however far the workflow got
    // (e.g. straight through to "Punch in confirmed").
    if (otpJustVerified) {
      backendMessage = `OTP verified. ${backendMessage}`;
    }

    setAutomationStatus(status);
    setAutomationStep(step);
    setAutomationMessage(backendMessage);

    if (status === "completed" || status === "success") {
      setMessage(backendMessage);
    }

    if (status === "failed" || status === "error") {
      setError(backendMessage);
    }
  };

  const handleAutomationResult = (result, actionName, options) => {
    const challengeId =
      result?.challenge_id ||
      result?.interrupt?.challenge_id ||
      result?.details?.challenge_id ||
      result?.details?.interrupt?.challenge_id;

    if (
      (result?.status === "waiting" ||
        result?.status === "otp_required" ||
        result?.status === "waiting_for_user") &&
      challengeId
    ) {
      setOtpChallengeId(challengeId);
      setOtpAction(actionName);
      setOtpError("");
      setAutomationStatus("waiting_for_user");
      setAutomationStep(result.current_step || "otp_waiting");
      setAutomationMessage(result.message || "Enter the OTP from the target site.");
      return;
    }

    processAutomationResult(result, actionName, options);
  };

  // Same synchronous double-click guard pattern as above -- the "Verify
  // OTP" button's disabled state also only takes effect after a re-render.
  const otpSubmitInFlightRef = useRef(false);


  const verifyAutomationOtp = async (otp) => {
    if (otpSubmitInFlightRef.current) return;

    const cleanOtp = String(otp || "").replace(/\D/g, "").slice(0, 6);

    if (!otpChallengeId) {
      setOtpError("OTP challenge is missing.");
      return;
    }

    if (!/^\d{6}$/.test(cleanOtp)) {
      setOtpError("Enter a valid 6-digit OTP.");
      return;
    }
    otpSubmitInFlightRef.current = true;
    otpVerificationActiveRef.current = true;

    setOtpBusy(true);
    setOtpError("");

    try {
      const result = await api.verifyOtp(
        sessionId,
        otpChallengeId,
        cleanOtp
      );

      const challengeId =
        result?.challenge_id ||
        result?.interrupt?.challenge_id ||
        result?.details?.challenge_id ||
        result?.details?.interrupt?.challenge_id;

      /*
       * OTP is still required / OTP was rejected.
       * Keep the popup open.
       */
      if (
        (result?.status === "waiting" ||
          result?.status === "otp_required" ||
          result?.status === "waiting_for_user") &&
        challengeId
      ) {
        setOtpChallengeId(challengeId);

        setOtpError(
          result?.otp_invalid
            ? "That OTP was not accepted. Please enter the latest OTP."
            : "A new OTP was requested. Please enter it."
        );

        return;
      }
      const otpVerified =
        result?.otp_verified === true ||
        result?.status === "otp_verified" ||
        result?.status === "verified";

      if (otpVerified) {
        // Close / hide OTP popup
        setOtpChallengeId(null);

        // Clear OTP-related state
        setOtpAction("");
        setOtpError("");
      }

      /*
       * Continue with the normal automation result handling.
       */
      handleAutomationResult(
        result,
        otpAction || "attendance action",
        {
          otpJustVerified: otpVerified,
        }
      );
    } catch (e) {
      if (e.status === 404) {
        logout();
        return;
      }

      setOtpError(e.message);
    } finally {
      otpSubmitInFlightRef.current = false;
      setOtpBusy(false);
    }
  };

  const action = async (name) => {
    if (actionInFlightRef.current) return;
    actionInFlightRef.current = true;

    setMessage("");
    setError("");
    setAutomationStatus("running");
    setAutomationStep("Getting current location");
    setAutomationMessage(
      "Requesting your current browser location..."
    );
    setBusyAction(name);

    try {
      const location = await getCurrentLocation();

      setAutomationStep("Location captured");
      setAutomationMessage(
        `Location captured • ±${Math.round(location.accuracy || 0)}m`
      );

      let result;

      if (name === "punch_in") {
        result = await api.punchIn(sessionId, location);
      } else {
        result = await api.punchOut(sessionId, location);
      }

      handleAutomationResult(result, name);
    } catch (e) {
      if (e.status === 404) {
        logout();
        return;
      }

      setAutomationStatus("failed");
      setError(e.message);
      setAutomationMessage(e.message);
    } finally {
      actionInFlightRef.current = false;
      setBusyAction("");
    }
  };

  useEffect(() => {
    // Keep polling live progress not only while the initial action call is
    // in flight (busyAction), but for the ENTIRE duration of the OTP-verify
    // call too (otpBusy). The backend keeps running the whole operation
    // (click_me -> time_attendance -> punch_in/out -> confirm) inside that
    // single /verify-otp request, which can take 30-60+ seconds. Without
    // polling here, the OTP modal just sat on a static "Verifying..."
    // message the whole time with no real feedback.
    if (!sessionId || (!busyAction && !otpBusy) || !api.getSessionStatus) return;

    let stopped = false;

    const poll = async () => {
      try {
        const result = await api.getSessionStatus(sessionId);

        if (stopped) return;

        if (result.status) {
          setAutomationStatus(result.status);
        }

        const statusChallengeId =
          result?.challenge_id ||
          result?.otp_challenge_id ||
          result?.details?.challenge_id;

        // Only treat this as a NEW OTP request if there isn't already one
        // open for the same challenge. Without this guard, this background
        // poller (which runs concurrently with the OTP modal's own
        // /verify-otp call, via otpBusy) can see a stale "waiting" snapshot
        // still sitting in session.workflow from just before OTP was
        // submitted, and redundantly reopen/reset the modal that the user
        // just successfully closed -- which is exactly the kind of "modal
        // won't close" glitch this guard prevents.
        const isGenuinelyNewChallenge =
          statusChallengeId && statusChallengeId !== otpChallengeIdRef.current;

        const isWaitingStatus =
          result?.status === "waiting" ||
          result?.status === "otp_required" ||
          result?.status === "waiting_for_user";

        if (isWaitingStatus && isGenuinelyNewChallenge) {
          console.info("[InfoTIME] OTP requested by backend; opening OTP popup");
          setOtpChallengeId(statusChallengeId);
          setOtpAction(result.operation || "attendance action");
          setOtpError("");
          setAutomationStatus("waiting_for_user");
          setAutomationStep(result.current_step || "otp_waiting");
          setAutomationMessage(
            result.message || "Enter the OTP you received by email."
          );
        }

        // Close the OTP popup purely off the polled backend status, as a
        // safety net independent of the /verify-otp response handling in
        // verifyAutomationOtp. This poller runs concurrently with that
        // request (via otpBusy) -- if the backend has already moved the
        // workflow PAST the OTP step (status is no longer one of the
        // waiting states: it reached "completed"/"success", is "running"
        // the rest of the flow, or "failed") while a popup is still open,
        // the challenge has been resolved server-side and the popup would
        // otherwise be left stuck open on stale state. This covers the
        // case where the direct /verify-otp response is slow, dropped, or
        // doesn't carry an explicit otp_verified flag for some reason --
        // the polled status alone is enough to know we're back at the
        // dashboard and the popup should close.
        if (otpChallengeIdRef.current && !isWaitingStatus) {
          console.info(
            "[InfoTIME] Backend status reached '%s'; closing OTP popup",
            result?.status
          );
          setOtpChallengeId(null);
          setOtpAction("");
          setOtpError("");
        }

        if (result.step || result.current_step) {
          setAutomationStep(result.step || result.current_step);
        }

        if (result.message) {
          setAutomationMessage(humanize(result.message));
        }

        if (result.error) {
          setError(result.error);
        }
      } catch (e) {
        if (e.status === 404) {
          console.warn("[InfoTIME] Session is no longer available on this backend instance");
          return;
        }

        // Status polling errors do not fail the main action.
      }
    };

    poll();

    const interval = setInterval(poll, 1500);

    return () => {
      stopped = true;
      clearInterval(interval);
    };
  }, [sessionId, busyAction, otpBusy]);

  const logout = () => {
    localStorage.removeItem("InfoTIME_session");
    localStorage.removeItem("InfoTIME_username");

    // Erase the accumulated steps log on logout -- it must not persist
    // into (or leak across) a new session.
    setStepsLog([]);

    if (onLogout) onLogout();
  };

  // Detect the backend going away (or the session becoming invalid) even
  // while the dashboard is just sitting idle -- not only while an action is
  // in flight. The poller above only runs during busyAction/otpBusy, so
  // without this, a disconnected backend would leave the dashboard showing
  // stale UI until the user next tried an action. This runs the whole time
  // the dashboard is mounted and sends the user back to the login page as
  // soon as the backend/session can't be confirmed.
  const sessionCheckFailuresRef = useRef(0);

  useEffect(() => {
    if (!sessionId) return;

    let stopped = false;

    const checkSession = async () => {
      try {
        await api.getSessionStatus(sessionId);
        sessionCheckFailuresRef.current = 0;
      } catch (e) {
        if (stopped) return;

        // A single dropped request (a brief network blip) shouldn't be
        // enough to boot the user -- require two consecutive failures
        // (covers both a 404 "session gone" response and the backend being
        // completely unreachable) before treating the session as invalid.
        sessionCheckFailuresRef.current += 1;

        if (sessionCheckFailuresRef.current >= 2) {
          logout();
        }
      }
    };

    const interval = setInterval(checkSession, 7000);

    return () => {
      stopped = true;
      clearInterval(interval);
    };
  }, [sessionId]);

  return (
    <div className="dashboard-shell">
      <header className="topbar">
        <div className="top-left">
          <Menu size={20} />

          <div className="small-brand">
            <div className="small-logo">
              <House size={18} />
            </div>
            <span>InfoTIME</span>
          </div>
        </div>
        <div className="top-right">
          <span className="muted">English</span>
          <Bell size={20} />

          <div className="avatar">
            <UserRound size={22} />
          </div>

          <button
            type="button"
            className="logout-button"
            onClick={logout}
            title="Logout"
          >
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="dashboard-main">
        <div className="profile-card">
          <div className="avatar-large">
            <UserRound size={40} />
          </div>

          <div>
            <h2>{username || "User"}</h2>
            <p>Active session</p>
          </div>

          <div className="active-pill">
            <span />
            Active
          </div>
        </div>

        <div className="dashboard-panels">
          <section className="panel">
            <h3 className="section-title">QUICK ACTIONS</h3>

            <div className="action-grid">
              <ActionCard
                className="blue"
                icon={<Clock3 />}
                title="Punch IN"
                subtitle={
                  busyAction === "punch_in"
                    ? "Processing..."
                    : "Start shift"
                }
                disabled={Boolean(busyAction)}
                onClick={() => action("punch_in")}
              />

              <ActionCard
                className="red"
                icon={<LogOut />}
                title="Punch OUT"
                subtitle={
                  busyAction === "punch_out"
                    ? "Processing..."
                    : "End shift"
                }
                disabled={Boolean(busyAction)}
                onClick={() => action("punch_out")}
              />

              <ActionCard
                className="green"
                icon={<House />}
                title="WFH-Work From Home"
                subtitle="Remote"
                disabled={Boolean(busyAction)}
                onClick={() => setWfhOpen(true)}
              />

              <ActionCard
                className="purple"
                icon={<CalendarDays />}
                title="Apply LEAVE"
                subtitle="Request off"
                disabled={Boolean(busyAction)}
                onClick={() =>
                  setMessage(
                    "Leave can use the same LLM automation pattern."
                  )
                }
              />
            </div>
          </section>

          <section className="panel">
            <h3 className="section-title">LIVE UPDATES</h3>

            <LiveUpdates
              status={automationStatus}
              step={automationStep}
              message={automationMessage}
              error={error}
            />

            <h3 className="section-title steps-log-title">STEPS</h3>
            <StepsLog steps={stepsLog} />
          </section>
        </div>

        {message && (
          <div className="toast">
            <CheckCircle2 size={18} />
            {message}
          </div>
        )}

        {error && !automationStatus && (
          <div className="error center">{error}</div>
        )}
      </main>

      {wfhOpen && (
        <WfhModal
          sessionId={sessionId}
          onClose={() => setWfhOpen(false)}
          onSuccess={(result) => {
            setMessage(
              result?.details?.status ||
                result?.message ||
                "WFH request submitted"
            );

            setAutomationStatus(result?.status || "completed");
            setAutomationStep(result?.step || "");
            setAutomationMessage(
              result?.message || "WFH request submitted"
            );

            // WfhModal only calls onSuccess for a real completion or a
            // hand-off to the OTP modal (see WfhModal.submit) -- a
            // backend-reported failure is handled inside WfhModal itself
            // so the error is visible and the form stays open. By the
            // time we get here, the form step is genuinely done, so
            // dismiss it and reveal the dashboard underneath.
            setWfhOpen(false);
            handleAutomationResult(result, "work_from_home");
          }}
        />
      )}

      {otpChallengeId && (
        <OtpModal
          onSubmit={verifyAutomationOtp}
          onCancel={async () => {
            try {
              await api.cancelSession(sessionId);
            } catch (e) {
              // Best-effort: still reset the local UI even if the backend
              // call fails (e.g. the browser session was already gone).
            }
            setOtpChallengeId(null);
            setOtpAction("");
            setOtpError("");
            setAutomationStatus("failed");
            setAutomationStep("");
            setAutomationMessage("Cancelled. You can start the action again.");
          }}
          busy={otpBusy}
          error={otpError}
          progressStep={automationStep}
          progressMessage={automationMessage}
        />
      )}
    </div>
  );
}

function ActionCard({
  className,
  icon,
  title,
  subtitle,
  onClick,
  disabled,
}) {
  return (
    <button
      className={`action-card ${className}`}
      disabled={disabled}
      onClick={onClick}
    >
      <div className="wave wave-a" />
      <div className="wave wave-b" />
      <div className="wave wave-c" />

      <div className="card-top">
        <div className="icon-circle">{icon}</div>
        <ArrowUpRight size={24} className="card-arrow" />
      </div>

      <div className="card-spacer" />

      <div className="card-copy">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
    </button>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(() =>
    localStorage.getItem("InfoTIME_session")
  );

  const [username, setUsername] = useState(() =>
    localStorage.getItem("InfoTIME_username") || ""
  );

  // A session ID sitting in localStorage only proves a session existed at
  // some point -- it says nothing about whether the backend still
  // recognizes it. The backend may have restarted, the session may have
  // expired, or the backend may simply be unreachable (e.g. the dev server
  // was stopped). Without checking, reopening the frontend would jump
  // straight to the Dashboard with a session that silently fails on the
  // first real action. `checkingSession` holds the Dashboard/Login decision
  // until that's actually been confirmed against the backend.
  const [checkingSession, setCheckingSession] = useState(
    () => !!localStorage.getItem("InfoTIME_session")
  );

  const clearStoredSession = () => {
    localStorage.removeItem("InfoTIME_session");
    localStorage.removeItem("InfoTIME_username");
    setSessionId(null);
    setUsername("");
  };

  useEffect(() => {
    const storedSessionId = localStorage.getItem("InfoTIME_session");

    if (!storedSessionId) {
      setCheckingSession(false);
      return;
    }

    let cancelled = false;

    api
      .getSessionStatus(storedSessionId)
      .then(() => {
        if (!cancelled) setCheckingSession(false);
      })
      .catch(() => {
        // Covers both cases: the backend explicitly rejected the session
        // (e.g. 404 / expired) and the backend being completely
        // unreachable (network error, backend process not running).
        // Either way there's no session to trust, so fall back to login.
        if (!cancelled) {
          clearStoredSession();
          setCheckingSession(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleAuthenticated = (id, name) => {
    localStorage.setItem("InfoTIME_session", id);
    localStorage.setItem("InfoTIME_username", name);

    setSessionId(id);
    setUsername(name);
  };

  const handleLogout = () => {
    clearStoredSession();
  };

  if (checkingSession) {
    return (
      <main className="auth-shell session-check">
        <div className="brand-block">
          <div className="logo-mark">
            <House size={32} />
          </div>
          <h1>InfoTIME</h1>
          <p>Enterprise Attendance Suite</p>
        </div>

        <div className="session-check-status">
          <Loader2 size={22} className="spin" />
          <span>Checking session...</span>
        </div>
      </main>
    );
  }

  if (!sessionId) {
    return <LoginPage onAuthenticated={handleAuthenticated} />;
  }

  return (
    <Dashboard
      sessionId={sessionId}
      username={username}
      onLogout={handleLogout}
    />
  );
}