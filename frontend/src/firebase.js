import { initializeApp, getApps } from "firebase/app";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
} from "firebase/auth";

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

if (isFirebaseConfigured) {
  app = getApps().length > 0 ? getApps()[0] : initializeApp(firebaseConfig);
  authInstance = getAuth(app);
}

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
    return onAuthStateChanged(authInstance, callback);
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
    return cred.user;
  }
  // Dev mode
  devUser = formatDevUser(email);
  localStorage.setItem("piyushai_dev_user", JSON.stringify({ uid: devUser.uid, email: devUser.email }));
  notifyDevListeners();
  return devUser;
}

export async function logInWithEmail(email, password) {
  if (isFirebaseConfigured && authInstance) {
    const cred = await signInWithEmailAndPassword(authInstance, email, password);
    return cred.user;
  }
  // Dev mode
  devUser = formatDevUser(email);
  localStorage.setItem("piyushai_dev_user", JSON.stringify({ uid: devUser.uid, email: devUser.email }));
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
