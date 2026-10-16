import { useEffect, useState } from "react";
import { logInWithEmail, signUpWithEmail, isFirebaseConfigured } from "./firebase.js";

function getErrorMessage(err) {
  const code = err.code || "";
  switch (code) {
    case "auth/invalid-email":
      return "Please enter a valid email address.";
    case "auth/user-not-found":
      return "No account found with this email.";
    case "auth/wrong-password":
    case "auth/invalid-credential":
      return "Incorrect email or password.";
    case "auth/email-already-in-use":
      return "An account with this email already exists. Try signing in.";
    case "auth/weak-password":
      return "Password must be at least 6 characters long.";
    case "auth/too-many-requests":
      return "Too many failed attempts. Please wait a few minutes and try again.";
    default:
      return err.message || "An authentication error occurred.";
  }
}

export default function AuthModal({ isOpen, onClose, onSuccess, initialTab = "login", reason = "" }) {
  const [tab, setTab] = useState(initialTab);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isOpen) {
      setTab(initialTab);
      setError("");
    }
  }, [isOpen, initialTab]);

  if (!isOpen) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError("Please enter your email.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }

    if (tab === "signup") {
      if (password.length < 6) {
        setError("Password must be at least 6 characters.");
        return;
      }
      if (password !== confirmPassword) {
        setError("Passwords do not match.");
        return;
      }
    }

    setLoading(true);
    try {
      let user;
      if (tab === "signup") {
        user = await signUpWithEmail(trimmedEmail, password);
      } else {
        user = await logInWithEmail(trimmedEmail, password);
      }
      onSuccess?.(user);
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-overlay" onClick={onClose}>
      <div className="auth-modal" onClick={(e) => e.stopPropagation()}>
        <button id="auth-modal-close" className="auth-close-btn" onClick={onClose} aria-label="Close modal">
          ✕
        </button>

        <div className="auth-header">
          <h2>{tab === "login" ? "Sign In to PiyushAI" : "Create your Account"}</h2>
          {reason ? (
            <p className="auth-reason">{reason}</p>
          ) : (
            <p className="auth-subtitle">
              Sign in to ask questions, explore GATE DA materials, and receive verified answers.
            </p>
          )}
        </div>

        {!isFirebaseConfigured && (
          <div className="auth-notice">
            <span className="notice-icon">ℹ️</span>
            <div>
              <strong>Dev Mode Active:</strong> Firebase API keys not set in <code>frontend/.env</code> yet. You can sign in/up with any email and password for local testing!
            </div>
          </div>
        )}

        <div className="auth-tabs">
          <button
            id="tab-sign-in"
            type="button"
            className={`auth-tab ${tab === "login" ? "active" : ""}`}
            onClick={() => {
              setTab("login");
              setError("");
            }}
          >
            Sign In
          </button>
          <button
            id="tab-sign-up"
            type="button"
            className={`auth-tab ${tab === "signup" ? "active" : ""}`}
            onClick={() => {
              setTab("signup");
              setError("");
            }}
          >
            Sign Up
          </button>
        </div>

        {error && <div className="auth-error-banner">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="auth-field">
            <label htmlFor="auth-email-input">Email Address</label>
            <input
              id="auth-email-input"
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              autoFocus
              required
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password-input">Password</label>
            <input
              id="auth-password-input"
              type="password"
              placeholder={tab === "signup" ? "At least 6 characters" : "Enter your password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          {tab === "signup" && (
            <div className="auth-field">
              <label htmlFor="auth-confirm-password-input">Confirm Password</label>
              <input
                id="auth-confirm-password-input"
                type="password"
                placeholder="Repeat your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={loading}
                required
              />
            </div>
          )}

          <button id="auth-submit-btn" type="submit" className="auth-submit-btn" disabled={loading}>
            {loading ? (
              <span className="btn-spinner">Processing…</span>
            ) : tab === "login" ? (
              "Sign In"
            ) : (
              "Create Account"
            )}
          </button>
        </form>

        <div className="auth-footer">
          {tab === "login" ? (
            <p>
              Don't have an account?{" "}
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  setTab("signup");
                  setError("");
                }}
              >
                Sign up here
              </button>
            </p>
          ) : (
            <p>
              Already have an account?{" "}
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  setTab("login");
                  setError("");
                }}
              >
                Sign in here
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
