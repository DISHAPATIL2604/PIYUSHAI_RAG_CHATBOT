import { initializeApp, getApps } from "firebase/app";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
} from "firebase/auth";
import {
  getFirestore,
  doc,
  setDoc,
  getDoc,
  collection,
  query,
  orderBy,
  getDocs,
  deleteDoc,
} from "firebase/firestore";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "",
};

export const isFirebaseConfigured = Boolean(
  firebaseConfig.apiKey &&
  firebaseConfig.projectId &&
  firebaseConfig.apiKey.trim() !== ""
);

let app = null;
let authInstance = null;
let firestoreDb = null;

if (isFirebaseConfigured) {
  app = getApps().length > 0 ? getApps()[0] : initializeApp(firebaseConfig);
  authInstance = getAuth(app);
  try {
    firestoreDb = getFirestore(app);
  } catch (err) {
    console.warn("Could not initialize Cloud Firestore client:", err);
  }
}

export const db = firestoreDb;

// Dev mock auth state for testing before real keys are set
let devUser = null;
const devListeners = new Set();

function formatDevUser(email, uid = null) {
  return {
    uid: uid || "dev-" + Math.random().toString(36).substring(2, 9),
    email,
    displayName: email.split("@")[0],
    getIdToken: async () => "mock-dev-token-" + Date.now(),
  };
}

function notifyDevListeners() {
  devListeners.forEach((cb) => {
    try {
      cb(devUser);
    } catch (e) {
      console.error(e);
    }
  });
}

export function subscribeToAuth(callback) {
  if (isFirebaseConfigured && authInstance) {
    return onAuthStateChanged(authInstance, (user) => {
      if (user) {
        initUserProfile(user).catch((err) => console.warn("Failed to init profile in Firestore:", err));
      }
      callback(user);
    });
  }

  // Fallback to local session storage for mock development
  const saved = localStorage.getItem("piyushai_dev_user");
  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      devUser = formatDevUser(parsed.email, parsed.uid);
    } catch {
      devUser = null;
    }
  }

  callback(devUser);
  devListeners.add(callback);
  return () => {
    devListeners.delete(callback);
  };
}

export async function signUpWithEmail(email, password) {
  if (isFirebaseConfigured && authInstance) {
    const cred = await createUserWithEmailAndPassword(authInstance, email, password);
    await initUserProfile(cred.user);
    return cred.user;
  }
  // Dev mode
  devUser = formatDevUser(email);
  localStorage.setItem("piyushai_dev_user", JSON.stringify({ uid: devUser.uid, email: devUser.email }));
  await initUserProfile(devUser);
  notifyDevListeners();
  return devUser;
}

export async function logInWithEmail(email, password) {
  if (isFirebaseConfigured && authInstance) {
    const cred = await signInWithEmailAndPassword(authInstance, email, password);
    await initUserProfile(cred.user);
    return cred.user;
  }
  // Dev mode
  devUser = formatDevUser(email);
  localStorage.setItem("piyushai_dev_user", JSON.stringify({ uid: devUser.uid, email: devUser.email }));
  await initUserProfile(devUser);
  notifyDevListeners();
  return devUser;
}

export async function logOut() {
  if (isFirebaseConfigured && authInstance) {
    return signOut(authInstance);
  }
  devUser = null;
  localStorage.removeItem("piyushai_dev_user");
  notifyDevListeners();
}

export async function getUserToken(user) {
  if (!user) return null;
  if (typeof user.getIdToken === "function") {
    try {
      return await user.getIdToken();
    } catch {
      return "mock-dev-token-" + Date.now();
    }
  }
  return "mock-dev-token-" + Date.now();
}

/* =========================================================================
   Cloud Firestore User Profile, Chats, and Messages Persistence
   ========================================================================= */

// Local storage fallback helpers for resilient offline/dev mode
function getLocalChats(uid) {
  try {
    return JSON.parse(localStorage.getItem(`piyushai_chats_${uid}`) || "[]");
  } catch {
    return [];
  }
}

function setLocalChats(uid, chats) {
  localStorage.setItem(`piyushai_chats_${uid}`, JSON.stringify(chats));
}

function getLocalMessages(uid, chatId) {
  try {
    return JSON.parse(localStorage.getItem(`piyushai_msgs_${uid}_${chatId}`) || "[]");
  } catch {
    return [];
  }
}

function setLocalMessages(uid, chatId, msgs) {
  localStorage.setItem(`piyushai_msgs_${uid}_${chatId}`, JSON.stringify(msgs));
}

/**
 * Initializes or updates user profile in Firestore under users/{uid}
 */
export async function initUserProfile(user, preferences = {}) {
  if (!user?.uid) return;
  const now = new Date().toISOString();
  const profileData = {
    uid: user.uid,
    email: user.email || "",
    displayName: user.displayName || (user.email ? user.email.split("@")[0] : "Learner"),
    updatedAt: now,
    preferences: preferences || {},
  };

  if (db) {
    try {
      const userRef = doc(db, "users", user.uid);
      const existing = await getDoc(userRef);
      if (!existing.exists()) {
        profileData.createdAt = now;
      }
      await setDoc(userRef, profileData, { merge: true });
      return;
    } catch (err) {
      console.warn("Firestore initUserProfile fallback to localStorage:", err);
    }
  }

  // Local fallback
  const localProf = JSON.parse(localStorage.getItem(`piyushai_user_${user.uid}`) || "{}");
  localStorage.setItem(
    `piyushai_user_${user.uid}`,
    JSON.stringify({
      ...profileData,
      createdAt: localProf.createdAt || now,
    })
  );
}

/**
 * Retrieves the list of user conversations from users/{uid}/chats
 */
export async function fetchUserChats(uid) {
  if (!uid) return [];
  if (db) {
    try {
      const chatsRef = collection(db, "users", uid, "chats");
      const q = query(chatsRef, orderBy("updatedAt", "desc"));
      const snapshot = await getDocs(q);
      const chats = [];
      snapshot.forEach((d) => chats.push({ chatId: d.id, ...d.data() }));
      return chats;
    } catch (err) {
      console.warn("Firestore fetchUserChats fallback to localStorage:", err);
    }
  }

  return getLocalChats(uid).sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
}

/**
 * Creates or updates a chat metadata record in users/{uid}/chats/{chatId}
 */
export async function createOrUpdateChat(uid, { chatId, title, selectedCourseId, selectedCourseName }) {
  if (!uid || !chatId) return;
  const now = new Date().toISOString();
  const chatData = {
    chatId,
    title: title || "New Conversation",
    selectedCourseId: selectedCourseId || null,
    selectedCourseName: selectedCourseName || null,
    updatedAt: now,
  };

  if (db) {
    try {
      const chatRef = doc(db, "users", uid, "chats", chatId);
      const existing = await getDoc(chatRef);
      if (!existing.exists()) {
        chatData.createdAt = now;
      }
      await setDoc(chatRef, chatData, { merge: true });
      return;
    } catch (err) {
      console.warn("Firestore createOrUpdateChat fallback to localStorage:", err);
    }
  }

  // Local fallback
  const chats = getLocalChats(uid);
  const idx = chats.findIndex((c) => c.chatId === chatId);
  if (idx >= 0) {
    chats[idx] = { ...chats[idx], ...chatData };
  } else {
    chats.unshift({ ...chatData, createdAt: now });
  }
  setLocalChats(uid, chats);
}

/**
 * Retrieves all messages for a chat from users/{uid}/chats/{chatId}/messages
 */
export async function fetchChatMessages(uid, chatId) {
  if (!uid || !chatId) return [];
  if (db) {
    try {
      const msgsRef = collection(db, "users", uid, "chats", chatId, "messages");
      const q = query(msgsRef, orderBy("timestamp", "asc"));
      const snapshot = await getDocs(q);
      const messages = [];
      snapshot.forEach((d) => messages.push({ messageId: d.id, ...d.data() }));
      return messages;
    } catch (err) {
      console.warn("Firestore fetchChatMessages fallback to localStorage:", err);
    }
  }

  return getLocalMessages(uid, chatId).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
}

/**
 * Appends a message to users/{uid}/chats/{chatId}/messages/{messageId}
 */
export async function saveChatMessage(uid, chatId, message) {
  if (!uid || !chatId || !message) return;
  const messageId = message.messageId || "msg_" + Date.now() + "_" + Math.random().toString(36).substring(2, 7);
  const now = message.timestamp || new Date().toISOString();

  const record = {
    messageId,
    role: message.role,
    content: message.content,
    timestamp: now,
    answer_mode: message.answer_mode || null,
    relatedResourceTitle: message.related_resource?.title || message.relatedResourceTitle || null,
    relatedResourceUrl: message.related_resource?.url || message.relatedResourceUrl || null,
    relatedResourceKind: message.related_resource?.kind || message.relatedResourceKind || null,
    relatedResourceReason: message.related_resource?.reason || message.relatedResourceReason || null,
    recommendedCourseId: message.recommended_course?.id || message.recommendedCourseId || null,
    recommendedCourseName: message.recommended_course?.title || message.recommendedCourseName || null,
    recommendedCourseUrl: message.recommended_course?.url || message.recommendedCourseUrl || null,
    recommendedCourseReason: message.recommended_course?.reason || message.recommendedCourseReason || null,
    sources: message.sources || [],
  };

  if (db) {
    try {
      // 1. Save message
      const msgRef = doc(db, "users", uid, "chats", chatId, "messages", messageId);
      await setDoc(msgRef, record);

      // 2. Touch chat updatedAt and update title if user message
      const chatRef = doc(db, "users", uid, "chats", chatId);
      const touchData = { updatedAt: now };
      if (message.role === "user") {
        const existing = await getDoc(chatRef);
        if (!existing.exists() || !existing.data().title || existing.data().title === "New Conversation") {
          touchData.title = message.content.slice(0, 48) + (message.content.length > 48 ? "…" : "");
        }
      }
      await setDoc(chatRef, touchData, { merge: true });
      return record;
    } catch (err) {
      console.warn("Firestore saveChatMessage fallback to localStorage:", err);
    }
  }

  // Local fallback
  const msgs = getLocalMessages(uid, chatId);
  // Avoid duplicate messageIds
  if (!msgs.some((m) => m.messageId === messageId)) {
    msgs.push(record);
    setLocalMessages(uid, chatId, msgs);
  }

  const chats = getLocalChats(uid);
  const cIdx = chats.findIndex((c) => c.chatId === chatId);
  if (cIdx >= 0) {
    chats[cIdx].updatedAt = now;
    if (message.role === "user" && (!chats[cIdx].title || chats[cIdx].title === "New Conversation")) {
      chats[cIdx].title = message.content.slice(0, 48) + (message.content.length > 48 ? "…" : "");
    }
    setLocalChats(uid, chats);
  }

  return record;
}

/**
 * Deletes a chat and its local record
 */
export async function deleteChat(uid, chatId) {
  if (!uid || !chatId) return;
  if (db) {
    try {
      const chatRef = doc(db, "users", uid, "chats", chatId);
      await deleteDoc(chatRef);
    } catch (err) {
      console.warn("Firestore deleteChat error:", err);
    }
  }

  const chats = getLocalChats(uid).filter((c) => c.chatId !== chatId);
  setLocalChats(uid, chats);
  localStorage.removeItem(`piyushai_msgs_${uid}_${chatId}`);
}
