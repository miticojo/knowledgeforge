import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

interface RuntimeConfig {
  firebaseApiKey: string;
  firebaseAuthDomain: string;
  firebaseProjectId: string;
  allowedEmails: string;
}

let cachedConfig: RuntimeConfig | null = null;

export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  if (cachedConfig) return cachedConfig;
  const res = await fetch("/api/config");
  cachedConfig = await res.json();
  return cachedConfig!;
}

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export async function initFirebase() {
  if (auth) return auth;
  const config = await getRuntimeConfig();
  if (!config.firebaseApiKey) return null;
  app = getApps().length === 0
    ? initializeApp({
        apiKey: config.firebaseApiKey,
        authDomain: config.firebaseAuthDomain,
        projectId: config.firebaseProjectId,
      })
    : getApps()[0];
  auth = getAuth(app);
  return auth;
}

export { auth };
