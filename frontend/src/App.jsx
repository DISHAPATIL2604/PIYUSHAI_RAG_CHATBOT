import { useEffect, useRef, useState } from "react";
import { deleteSession, getCourses, getSubjects, sendChat } from "./api.js";
import { getUserToken, logOut, subscribeToAuth } from "./firebase.js";
import AuthModal from "./AuthModal.jsx";

const MODE_LABEL = {
  grounded: "Grounded in PiyushAI sources",
  general_knowledge: "General explanation (not from PiyushAI sources)",
  not_found: "Not found in indexed PiyushAI sources",
};

function Recommendation({ title, rec }) {
  if (!rec) return null;
  return (
    <div className="rec">
      <strong>{title}:</strong>{" "}
      <a href={rec.url} target="_blank" rel="noopener noreferrer">{rec.title}</a>
      {rec.is_sample && <span className="badge">SAMPLE DATA</span>}
      <div className="muted">{rec.reason}</div>
    </div>
  );
}

function Message({ m, onFollowUp, disabled }) {
  if (m.role === "user") return <div className="msg user">{m.content}</div>;
  return (
    <div className="msg assistant">
      <div className={`mode mode-${m.answer_mode}`}>{MODE_LABEL[m.answer_mode] || m.answer_mode}</div>
      <div className="answer">{m.content}</div>
      {m.sources?.length > 0 && (
        <div className="sources">
          <strong>Sources</strong>
          <ul>
            {m.sources.map((s) => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || s.url}</a>
                <span className="muted"> ({s.content_type})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Recommendation title="Recommended course" rec={m.course_recommendation} />
      <Recommendation title="Recommended video" rec={m.youtube_recommendation} />
      {m.suggested_follow_up_questions?.length > 0 && (
        <div className="chips">
          {m.suggested_follow_up_questions.map((q) => (
            <button key={q} className="chip" disabled={disabled} onClick={() => onFollowUp(q)}>{q}</button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authModalTab, setAuthModalTab] = useState("login");
  const [authReason, setAuthReason] = useState("");
  const [pendingText, setPendingText] = useState("");

  const [exams, setExams] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [course, setCourse] = useState("");
  const [subject, setSubject] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(() => sessionStorage.getItem("piyushai_session") || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    const unsub = subscribeToAuth((user) => {
      setCurrentUser(user);
      setAuthLoading(false);
    });
    return () => {
      if (typeof unsub === "function") unsub();
    };
  }, []);

  useEffect(() => {
    getCourses()
      .then((d) => {
        setExams(d.exams);
        if (d.exams.length) setCourse(d.exams[0]);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!course) return;
    getSubjects(course).then((d) => setSubjects(d.subjects.map((s) => s.name))).catch((e) => setError(e.message));
    setSubject("");
  }, [course]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function requireAuth(reason = "Please sign in to ask questions.") {
    setAuthReason(reason);
    setAuthModalTab("login");
    setAuthModalOpen(true);
  }

  async function send(text, activeUser = currentUser) {
    const message = (text ?? input).trim();
    if (!message || loading) return;

    if (!activeUser) {
      setPendingText(message);
      requireAuth("Please sign in or create an account before asking questions.");
      return;
    }

    setError("");
    setInput("");
    setPendingText("");
    setMessages((m) => [...m, { role: "user", content: message }]);
    setLoading(true);

    try {
      const token = await getUserToken(activeUser);
      const res = await sendChat({
        session_id: sessionId,
        message,
        selected_course: course || null,
        selected_subject: subject || null,
      }, token);

      setSessionId(res.session_id);
      sessionStorage.setItem("piyushai_session", res.session_id);
      setMessages((m) => [...m, { role: "assistant", content: res.answer, ...res }]);
    } catch (e) {
      if (e.status === 401) {
        requireAuth("Your session expired or token is invalid. Please sign in again.");
      }
      setError(e.retryAfter ? `${e.message} (retry in ~${e.retryAfter}s)` : e.message);
    } finally {
      setLoading(false);
    }
  }

  async function reset() {
    if (sessionId) {
      const token = currentUser ? await getUserToken(currentUser) : null;
      await deleteSession(sessionId, token).catch(() => {});
    }
    sessionStorage.removeItem("piyushai_session");
    setSessionId(null);
    setMessages([]);
    setError("");
  }

  function handleAuthSuccess(user) {
    setCurrentUser(user);
    if (pendingText) {
      const textToRun = pendingText;
      setPendingText("");
      setTimeout(() => {
        send(textToRun, user);
      }, 100);
    }
  }

  return (
    <div className="app">
      <header>
        <div className="header-left">
          <h1>PiyushAI Assistant</h1>
          <span className="header-badge">GATE DA & Course AI</span>
        </div>

        <div className="header-actions">
          {authLoading ? (
            <span className="auth-status-loading">Checking auth…</span>
          ) : currentUser ? (
            <div className="user-profile">
              <span className="user-avatar" title={currentUser.email}>
                {(currentUser.displayName || currentUser.email || "U")[0].toUpperCase()}
              </span>
              <span className="user-email">{currentUser.email || currentUser.displayName}</span>
              <button
                id="btn-sign-out"
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => logOut()}
                title="Sign out of your account"
              >
                Sign out
              </button>
            </div>
          ) : (
            <div className="auth-buttons">
              <button
                id="btn-header-sign-in"
                type="button"
                className="btn-primary btn-sm"
                onClick={() => {
                  setAuthReason("");
                  setAuthModalTab("login");
                  setAuthModalOpen(true);
                }}
              >
                Sign In
              </button>
              <button
                id="btn-header-sign-up"
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => {
                  setAuthReason("");
                  setAuthModalTab("signup");
                  setAuthModalOpen(true);
                }}
              >
                Sign Up
              </button>
            </div>
          )}

          <button id="btn-reset-chat" onClick={reset} disabled={loading} className="btn-secondary btn-sm">
            Reset
          </button>
        </div>
      </header>

      <div className="controls">
        <label>
          Course
          <select value={course} onChange={(e) => setCourse(e.target.value)}>
            {exams.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label>
          Subject
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">(any subject)</option>
            {subjects.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
      </div>

      <div className="chat">
        {!currentUser && (
          <div className="auth-prompt-card">
            <div className="auth-prompt-icon">🔐</div>
            <div className="auth-prompt-content">
              <h3>Authentication Required</h3>
              <p>
                Please sign in or create an account to start chatting. The chatbot verifies your secure authentication tokens before processing and answering questions.
              </p>
              <div className="auth-prompt-buttons">
                <button
                  id="btn-prompt-sign-in"
                  type="button"
                  className="btn-primary"
                  onClick={() => {
                    setAuthReason("Please sign in to ask questions.");
                    setAuthModalTab("login");
                    setAuthModalOpen(true);
                  }}
                >
                  Sign In to Chat
                </button>
                <button
                  id="btn-prompt-sign-up"
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setAuthReason("Create an account to start asking questions.");
                    setAuthModalTab("signup");
                    setAuthModalOpen(true);
                  }}
                >
                  Create Account
                </button>
              </div>
            </div>
          </div>
        )}

        {messages.length === 0 && currentUser && (
          <p className="muted">Ask about PiyushAI courses or a GATE DA topic.</p>
        )}

        {messages.map((m, i) => (
          <Message key={i} m={m} onFollowUp={send} disabled={loading} />
        ))}

        {loading && <div className="loading">Thinking…</div>}
        <div ref={endRef} />
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      <div className="composer">
        <input
          id="composer-input"
          value={input}
          placeholder={currentUser ? "Type your question…" : "Sign in to ask a question…"}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={loading}
        />
        <button
          id="btn-send-message"
          onClick={() => send()}
          disabled={loading || !input.trim()}
          className={!currentUser ? "btn-auth-required" : ""}
          title={!currentUser ? "Sign in to send" : "Send message"}
        >
          {currentUser ? "Send" : "Sign in to Send"}
        </button>
      </div>

      <AuthModal
        isOpen={authModalOpen}
        initialTab={authModalTab}
        reason={authReason}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={handleAuthSuccess}
      />
    </div>
  );
}
