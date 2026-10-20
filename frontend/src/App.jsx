import { useEffect, useRef, useState } from "react";
import { getCourses, getSubjects, sendChat } from "./api.js";
import {
  createOrUpdateChat,
  deleteChat,
  fetchChatMessages,
  fetchUserChats,
  getUserToken,
  initUserProfile,
  logOut,
  saveChatMessage,
  subscribeToAuth,
} from "./firebase.js";
import AuthModal from "./AuthModal.jsx";

const MODE_LABEL = {
  grounded: "Grounded in PiyushAI sources",
  general_knowledge: "General explanation (not from PiyushAI sources)",
  not_found: "Not found in indexed PiyushAI sources",
};

function formatTimestamp(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function formatChatDate(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

/* -------------------------------------------------------------------------
   Recommendation Components: Verified Resource & Verified Course
   ------------------------------------------------------------------------- */

function RelatedResourceCard({ resource }) {
  if (!resource || !resource.url) return null;

  const kindLabel =
    resource.kind === "video"
      ? "Video Tutorial"
      : resource.kind === "article"
      ? "PiyushAI Article"
      : "PiyushAI Resource";

  const kindIcon = resource.kind === "video" ? "📺" : "📄";

  return (
    <div className="recommendation-card resource-card">
      <div className="card-header">
        <span className="card-badge resource-badge">
          {kindIcon} {kindLabel}
        </span>
        {resource.is_sample && <span className="sample-badge">SAMPLE DATA</span>}
      </div>
      <div className="card-body">
        <h4 className="card-title">
          <a href={resource.url} target="_blank" rel="noopener noreferrer">
            {resource.title || resource.url}
            <span className="external-icon">↗</span>
          </a>
        </h4>
        {resource.reason && <p className="card-reason">{resource.reason}</p>}
      </div>
    </div>
  );
}

function RecommendedCourseCard({ course }) {
  if (!course || !course.url) return null;

  return (
    <div className="recommendation-card course-card">
      <div className="card-header">
        <span className="card-badge course-badge">🎓 Recommended PiyushAI Course</span>
        {course.is_sample && <span className="sample-badge">SAMPLE DATA</span>}
      </div>
      <div className="card-body">
        <h4 className="card-title">
          <a href={course.url} target="_blank" rel="noopener noreferrer">
            {course.title}
            <span className="external-icon">↗</span>
          </a>
        </h4>
        {course.reason && <p className="card-reason">{course.reason}</p>}
        <div className="card-actions">
          <a
            href={course.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-course-cta"
          >
            View Course Curriculum & Details →
          </a>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------
   Message Item Component
   ------------------------------------------------------------------------- */

function MessageItem({ m }) {
  if (m.role === "user") {
    return (
      <div className="msg user">
        <div className="msg-content">{m.content}</div>
        {m.timestamp && <div className="msg-time">{formatTimestamp(m.timestamp)}</div>}
      </div>
    );
  }

  // Normalise recommendations whether from Firestore message or fresh backend response
  const resource = m.related_resource || (m.relatedResourceUrl ? {
    title: m.relatedResourceTitle,
    url: m.relatedResourceUrl,
    kind: m.relatedResourceKind || "article",
    reason: m.relatedResourceReason,
    is_sample: false,
  } : null) || (m.youtube_recommendation ? {
    title: m.youtube_recommendation.title,
    url: m.youtube_recommendation.url,
    kind: "video",
    reason: m.youtube_recommendation.reason,
    is_sample: m.youtube_recommendation.is_sample,
  } : null);

  const course = m.recommended_course || (m.recommendedCourseUrl ? {
    id: m.recommendedCourseId,
    title: m.recommendedCourseName,
    url: m.recommendedCourseUrl,
    reason: m.recommendedCourseReason,
    is_sample: false,
  } : null) || (m.course_recommendation ? {
    id: m.course_recommendation.id,
    title: m.course_recommendation.title,
    url: m.course_recommendation.url,
    reason: m.course_recommendation.reason,
    is_sample: m.course_recommendation.is_sample,
  } : null);

  return (
    <div className="msg assistant">
      {m.answer_mode && (
        <div className={`mode mode-${m.answer_mode}`}>
          {MODE_LABEL[m.answer_mode] || m.answer_mode}
        </div>
      )}

      {/* 1. Direct Answer */}
      <div className="msg-content answer-text">{m.content}</div>

      {/* 2. Related PiyushAI Resource */}
      <RelatedResourceCard resource={resource} />

      {/* 3. Recommended PiyushAI Course */}
      <RecommendedCourseCard course={course} />

      {/* Verified Sources list (if grounded) */}
      {m.sources?.length > 0 && (
        <details className="sources-details">
          <summary className="sources-summary">
            Verified Indexed Sources ({m.sources.length})
          </summary>
          <ul className="sources-list">
            {m.sources.map((s) => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noopener noreferrer">
                  {s.title || s.url}
                </a>
                <span className="muted"> ({s.content_type || "verified page"})</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {m.timestamp && <div className="msg-time">{formatTimestamp(m.timestamp)}</div>}
    </div>
  );
}

/* -------------------------------------------------------------------------
   Main App Component
   ------------------------------------------------------------------------- */

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

  const [chatList, setChatList] = useState([]);
  const [activeChatId, setActiveChatId] = useState(() => sessionStorage.getItem("piyushai_active_chat") || null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);

  // Subscribe to Auth state
  useEffect(() => {
    const unsub = subscribeToAuth((user) => {
      setCurrentUser(user);
      setAuthLoading(false);
      if (user) {
        initUserProfile(user);
        loadUserChats(user.uid);
      } else {
        setChatList([]);
        setMessages([]);
        setActiveChatId(null);
        sessionStorage.removeItem("piyushai_active_chat");
      }
    });
    return () => {
      if (typeof unsub === "function") unsub();
    };
  }, []);

  // Load Exam / Course categories
  useEffect(() => {
    getCourses()
      .then((d) => {
        setExams(d.exams || []);
        if (d.exams?.length && !course) setCourse(d.exams[0]);
      })
      .catch((e) => setError(e.message));
  }, []);

  // Load Subjects when course changes
  useEffect(() => {
    if (!course) return;
    getSubjects(course)
      .then((d) => setSubjects(d.subjects.map((s) => s.name)))
      .catch((e) => setError(e.message));
    setSubject("");
  }, [course]);

  // Auto-scroll chat to latest message
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Load list of chats for the user
  async function loadUserChats(uid) {
    if (!uid) return;
    try {
      const chats = await fetchUserChats(uid);
      setChatList(chats);

      // If activeChatId exists, restore its messages
      const currentActive = sessionStorage.getItem("piyushai_active_chat");
      if (currentActive && chats.some((c) => c.chatId === currentActive)) {
        loadConversation(currentActive, uid);
      }
    } catch (err) {
      console.warn("Error loading user chats:", err);
    }
  }

  // Load a specific conversation's messages
  async function loadConversation(chatId, uid = currentUser?.uid) {
    if (!chatId || !uid) return;
    setActiveChatId(chatId);
    sessionStorage.setItem("piyushai_active_chat", chatId);
    setHistoryLoading(true);
    setError("");

    try {
      const msgs = await fetchChatMessages(uid, chatId);
      setMessages(msgs);
    } catch (err) {
      console.error("Error loading chat messages:", err);
      setError("Failed to restore previous conversation messages.");
    } finally {
      setHistoryLoading(false);
    }
  }

  // Start a fresh conversation
  function handleNewChat() {
    setActiveChatId(null);
    sessionStorage.removeItem("piyushai_active_chat");
    setMessages([]);
    setInput("");
    setError("");
  }

  // Delete a conversation
  async function handleDeleteChat(e, chatId) {
    e.stopPropagation();
    if (!currentUser) return;
    if (!window.confirm("Are you sure you want to delete this conversation?")) return;

    try {
      await deleteChat(currentUser.uid, chatId);
      setChatList((prev) => prev.filter((c) => c.chatId !== chatId));
      if (activeChatId === chatId) {
        handleNewChat();
      }
    } catch (err) {
      console.error("Error deleting chat:", err);
    }
  }

  function requireAuth(reason = "Please sign in to ask questions.") {
    setAuthReason(reason);
    setAuthModalTab("login");
    setAuthModalOpen(true);
  }

  // Send question
  async function send(text, activeUser = currentUser) {
    const question = (text ?? input).trim();
    if (!question || loading) return;

    if (!activeUser) {
      setPendingText(question);
      requireAuth("Please sign in or create an account before asking questions.");
      return;
    }

    setError("");
    setInput("");
    setPendingText("");

    // Determine or create chatId
    let currentChatId = activeChatId;
    const isNew = !currentChatId;
    if (!currentChatId) {
      currentChatId = "chat_" + Date.now() + "_" + Math.random().toString(36).substring(2, 8);
      setActiveChatId(currentChatId);
      sessionStorage.setItem("piyushai_active_chat", currentChatId);

      // Create conversation document in Firestore
      await createOrUpdateChat(activeUser.uid, {
        chatId: currentChatId,
        title: question.slice(0, 48) + (question.length > 48 ? "…" : ""),
        selectedCourseId: course || null,
        selectedCourseName: course || null,
      });
    }

    // Create and save user message
    const userMsg = {
      messageId: "msg_user_" + Date.now(),
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    // Persist user message to Firestore
    saveChatMessage(activeUser.uid, currentChatId, userMsg).catch((err) =>
      console.warn("Could not persist user message:", err)
    );

    try {
      const token = await getUserToken(activeUser);
      const res = await sendChat(
        {
          session_id: currentChatId,
          message: question,
          selected_course: course || null,
          selected_subject: subject || null,
        },
        token
      );

      // Create assistant message with verified recommendation metadata
      const assistantMsg = {
        messageId: "msg_asst_" + Date.now(),
        role: "assistant",
        content: res.answer,
        answer_mode: res.answer_mode,
        timestamp: new Date().toISOString(),
        related_resource: res.related_resource || null,
        recommended_course: res.recommended_course || null,
        course_recommendation: res.course_recommendation || null,
        youtube_recommendation: res.youtube_recommendation || null,
        sources: res.sources || [],
      };

      setMessages((prev) => [...prev, assistantMsg]);

      // Persist assistant message to Firestore
      await saveChatMessage(activeUser.uid, currentChatId, assistantMsg);

      // Refresh chat list to update timestamps and titles
      const updatedChats = await fetchUserChats(activeUser.uid);
      setChatList(updatedChats);
    } catch (e) {
      if (e.status === 401) {
        requireAuth("Your session expired or token is invalid. Please sign in again.");
      }
      setError(e.retryAfter ? `${e.message} (retry in ~${e.retryAfter}s)` : e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleAuthSuccess(user) {
    setCurrentUser(user);
    initUserProfile(user);
    loadUserChats(user.uid);
    if (pendingText) {
      const textToRun = pendingText;
      setPendingText("");
      setTimeout(() => {
        send(textToRun, user);
      }, 100);
    }
  }

  return (
    <div className={`app-layout ${sidebarOpen ? "sidebar-visible" : "sidebar-collapsed"}`}>
      {/* -----------------------------------------------------------------
          Left Sidebar: Persistent Chat History
          ----------------------------------------------------------------- */}
      <aside className="chat-sidebar">
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <span className="brand-icon">⚡</span>
            <span className="brand-text">PiyushAI Chat</span>
          </div>
          <button
            id="btn-new-chat"
            className="btn-new-chat"
            onClick={handleNewChat}
            title="Start a new chat conversation"
          >
            + New Chat
          </button>
        </div>

        <div className="sidebar-history">
          <div className="history-label">Previous Conversations</div>

          {!currentUser ? (
            <div className="sidebar-guest-notice">
              <p>Sign in to view and save your conversation history.</p>
              <button
                className="btn-primary btn-sm full-width"
                onClick={() => {
                  setAuthReason("Sign in to access your saved chat history.");
                  setAuthModalTab("login");
                  setAuthModalOpen(true);
                }}
              >
                Sign In
              </button>
            </div>
          ) : chatList.length === 0 ? (
            <div className="history-empty">No saved chats yet. Start chatting!</div>
          ) : (
            <ul className="chat-history-list">
              {chatList.map((c) => (
                <li
                  key={c.chatId}
                  className={`chat-history-item ${activeChatId === c.chatId ? "active" : ""}`}
                  onClick={() => loadConversation(c.chatId)}
                >
                  <div className="chat-item-main">
                    <span className="chat-item-icon">💬</span>
                    <span className="chat-item-title" title={c.title || "Conversation"}>
                      {c.title || "Conversation"}
                    </span>
                  </div>
                  <div className="chat-item-meta">
                    <span className="chat-item-time">{formatChatDate(c.updatedAt || c.createdAt)}</span>
                    <button
                      className="btn-delete-chat"
                      title="Delete chat"
                      onClick={(e) => handleDeleteChat(e, c.chatId)}
                    >
                      ×
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* -----------------------------------------------------------------
          Main Chat Container
          ----------------------------------------------------------------- */}
      <main className="chat-main">
        <header>
          <div className="header-left">
            <button
              id="btn-toggle-sidebar"
              className="btn-sidebar-toggle"
              onClick={() => setSidebarOpen((prev) => !prev)}
              title="Toggle conversation history sidebar"
            >
              ☰
            </button>
            <div>
              <h1>PiyushAI Assistant</h1>
              <span className="header-badge">GATE DA & Course AI</span>
            </div>
          </div>

          <div className="header-actions">
            {authLoading ? (
              <span className="auth-status-loading">Checking auth…</span>
            ) : currentUser ? (
              <div className="user-profile">
                <span className="user-avatar" title={currentUser.email}>
                  {(currentUser.displayName || currentUser.email || "U")[0].toUpperCase()}
                </span>
                <span className="user-email">{currentUser.displayName || currentUser.email}</span>
                <button
                  id="btn-sign-out"
                  type="button"
                  className="btn-secondary btn-sm"
                  onClick={() => logOut()}
                  title="Sign out of your account"
                >
                  Sign Out
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
          </div>
        </header>

        {/* Filter controls */}
        <div className="controls">
          <label>
            Course Context
            <select value={course} onChange={(e) => setCourse(e.target.value)}>
              {exams.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label>
            Subject Filter
            <select value={subject} onChange={(e) => setSubject(e.target.value)}>
              <option value="">(any subject)</option>
              {subjects.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Chat Messages */}
        <div className="chat">
          {!currentUser && (
            <div className="auth-prompt-card">
              <div className="auth-prompt-icon">🔐</div>
              <div className="auth-prompt-content">
                <h3>Authentication Required</h3>
                <p>
                  Please sign in or create an account to start chatting. The chatbot verifies your secure authentication tokens before processing questions and persists your conversations securely.
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

          {historyLoading ? (
            <div className="loading">Restoring conversation messages…</div>
          ) : messages.length === 0 && currentUser ? (
            <div className="welcome-box">
              <h3>Welcome to PiyushAI Assistant</h3>
              <p>
                Ask any question about GATE Data Science & AI (DA), such as Probability, Linear Algebra, Machine Learning, or PiyushAI Courses.
              </p>
              <div className="example-queries">
                <button
                  className="example-chip"
                  onClick={() => setInput("How to compute eigenvalues and eigenvectors of a matrix?")}
                >
                  💡 How to compute eigenvalues and eigenvectors?
                </button>
                <button
                  className="example-chip"
                  onClick={() => setInput("Explain Bayes Theorem with a worked example.")}
                >
                  💡 Explain Bayes Theorem with an example
                </button>
                <button
                  className="example-chip"
                  onClick={() => setInput("What topics are covered in the GATE DA course?")}
                >
                  💡 What topics are covered in the GATE DA course?
                </button>
              </div>
            </div>
          ) : null}

          {messages.map((m, i) => (
            <MessageItem key={m.messageId || i} m={m} />
          ))}

          {loading && <div className="loading">Thinking & retrieving verified PiyushAI resources…</div>}
          <div ref={endRef} />
        </div>

        {error && <div className="error" role="alert">{error}</div>}

        {/* Message Input Composer */}
        <div className="composer">
          <input
            id="composer-input"
            value={input}
            placeholder={currentUser ? "Ask a question about GATE DA or PiyushAI courses…" : "Sign in to ask a question…"}
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
      </main>

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
