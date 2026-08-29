import React, { useEffect, useState } from "react";
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
function OtpModal({ onSubmit, busy, error }) {
  const [otp, setOtp] = useState("");

  return (
    <div className="modal-backdrop">
      <div className="modal-card otp-card">
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
          <p className="pin-hint">
            This is only needed once per session — hang tight while we
            finish the request.
          </p>
        )}
      </div>
    </div>
  );
}

function AutomationStatus({ status, step, message, error }) {
  if (!status && !step && !message && !error) return null;

  const completed = status === "completed" || status === "success";
  const failed = status === "failed" || status === "error";
  const waiting = status === "waiting_for_user" || status === "waiting";
  const running =
    status === "running" || status === "in_progress" || status === "recovering";

  return (
    <div className="automation-status">
      <div className="automation-status-header">
        <div className="automation-status-title">
          {completed && <CheckCircle2 size={20} />}
          {failed && <AlertCircle size={20} />}
          {(running || waiting) && <Loader2 size={20} className="spin" />}
          {!completed && !failed && !running && !waiting && <Clock3 size={20} />}

          <strong>
            {completed
              ? "Automation completed"
              : failed
              ? "Automation failed"
              : waiting
              ? "Waiting for OTP"
              : "Automation in progress"}
          </strong>
        </div>
      </div>

      {step && (
        <div className="automation-step">
          <span className="automation-step-label">Current step</span>
          <span className="automation-step-value">{step}</span>
        </div>
      )}

      {message && <div className="automation-message">{message}</div>}

      {error && (
        <div className="automation-error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
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

  const submit = async () => {
    setError("");

    if (!startDate || !endDate || !reason.trim()) {
      setError("Start date, end date and reason are required.");
      return;
    }

    if (new Date(endDate) < new Date(startDate)) {
      setError("End date cannot be before start date.");
      return;
    }

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

      onSuccess(result);
    } catch (e) {
      setError(e.message);
      setLocationStatus("Location not captured");
    } finally {
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

      localStorage.setItem("attendease_username", loggedInUsername);

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
          <h1>AttendEase</h1>
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
        <h1>AttendEase</h1>
        <p>Enterprise Attendance Suite</p>
      </div>

      <div className="form-stack">
        <label>TARGET SITE USERNAME</label>

        <input
          className="text-input"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Enter target site username"
          disabled={step === "register-password"}
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
              placeholder="Password for target site"
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
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [automationStatus, setAutomationStatus] = useState(null);
  const [automationStep, setAutomationStep] = useState("");
  const [automationMessage, setAutomationMessage] = useState("");
  const [otpChallengeId, setOtpChallengeId] = useState(null);
  const [otpAction, setOtpAction] = useState("");
  const [otpBusy, setOtpBusy] = useState(false);
  const [otpError, setOtpError] = useState("");

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

  const verifyAutomationOtp = async (otp) => {
    const cleanOtp = String(otp || "").replace(/\D/g, "").slice(0, 6);

    if (!otpChallengeId) {
      setOtpError("OTP challenge is missing.");
      return;
    }

    if (!/^\d{6}$/.test(cleanOtp)) {
      setOtpError("Enter a valid 6-digit OTP.");
      return;
    }

    setOtpBusy(true);
    setOtpError("");

    try {
      // NOTE: the backend keeps running the SAME operation (punch in / punch
      // out / work from home) to completion inside this single request once
      // the OTP is accepted -- it does not stop at "OTP verified". The
      // response therefore already reflects the real, final workflow status
      // (e.g. "completed"), not just the OTP outcome.
      const result = await api.verifyOtp(sessionId, otpChallengeId, cleanOtp);

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
        // The target site rejected the OTP (or asked for a new one).
        // Keep the same modal open with the new/refreshed challenge.
        setOtpChallengeId(challengeId);
        setOtpError(
          result?.otp_invalid
            ? "That OTP was not accepted. Please enter the latest OTP."
            : "A new OTP was requested. Please enter it."
        );
        return;
      }

      setOtpChallengeId(null);
      setOtpAction("");
      handleAutomationResult(result, otpAction || "attendance action", {
        otpJustVerified: Boolean(result?.otp_verified),
      });
    } catch (e) {
      if (e.status === 404) {
        logout();
        return;
      }

      setOtpError(e.message);
    } finally {
      setOtpBusy(false);
    }
  };

  const action = async (name) => {
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
      setBusyAction("");
    }
  };

  useEffect(() => {
    if (!sessionId || !busyAction || !api.getSessionStatus) return;

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

        if (
          (result?.status === "waiting" ||
            result?.status === "otp_required" ||
            result?.status === "waiting_for_user") &&
          statusChallengeId
        ) {
          console.info("[AttendEase] OTP requested by backend; opening OTP popup");
          setOtpChallengeId(statusChallengeId);
          setOtpAction(result.operation || "attendance action");
          setOtpError("");
          setAutomationStatus("waiting_for_user");
          setAutomationStep(result.current_step || "otp_waiting");
          setAutomationMessage(
            result.message || "Enter the OTP you received by email."
          );
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
          console.warn("[AttendEase] Session is no longer available on this backend instance");
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
  }, [sessionId, busyAction]);

  const logout = () => {
    localStorage.removeItem("attendease_session");
    localStorage.removeItem("attendease_username");

    if (onLogout) onLogout();
  };

  return (
    <div className="dashboard-shell">
      <header className="topbar">
        <div className="top-left">
          <Menu size={20} />

          <div className="small-brand">
            <div className="small-logo">
              <House size={18} />
            </div>
            <span>AttendEase</span>
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

        <h3 className="section-title">QUICK ACTIONS</h3>

        <div className="action-grid">
          <ActionCard
            className="blue"
            icon={<Clock3 />}
            title="Punch In"
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
            title="Punch Out"
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
            title="Remote"
            subtitle="Work from home"
            disabled={Boolean(busyAction)}
            onClick={() => setWfhOpen(true)}
          />

          <ActionCard
            className="purple"
            icon={<CalendarDays />}
            title="Leave"
            subtitle="Request off"
            disabled={Boolean(busyAction)}
            onClick={() =>
              setMessage(
                "Leave can use the same LLM automation pattern."
              )
            }
          />
        </div>

        <AutomationStatus
          status={automationStatus}
          step={automationStep}
          message={automationMessage}
          error={error}
        />

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

            setWfhOpen(false);
            handleAutomationResult(result, "work_from_home");
          }}
        />
      )}

      {otpChallengeId && (
        <OtpModal
          onSubmit={verifyAutomationOtp}
          busy={otpBusy}
          error={otpError}
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
        <ArrowUpRight size={24} />
      </div>

      <div className="card-copy">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
    </button>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(() =>
    localStorage.getItem("attendease_session")
  );

  const [username, setUsername] = useState(() =>
    localStorage.getItem("attendease_username") || ""
  );

  const handleAuthenticated = (id, name) => {
    localStorage.setItem("attendease_session", id);
    localStorage.setItem("attendease_username", name);

    setSessionId(id);
    setUsername(name);
  };

  const handleLogout = () => {
    setSessionId(null);
    setUsername("");
  };

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
