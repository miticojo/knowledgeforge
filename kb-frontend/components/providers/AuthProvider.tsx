"use client";

import React, { createContext, useContext, useEffect, useState, useRef } from "react";
import { onAuthStateChanged, User, signInWithPopup, GoogleAuthProvider, signOut, type Auth } from "firebase/auth";
import { initFirebase, getRuntimeConfig } from "@/lib/firebase";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  signIn: () => Promise<void>;
  logOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  signIn: async () => {},
  logOut: async () => {}
});

function LoginScreen({ onSignIn, error }: { onSignIn: () => void; error: string | null }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--background)]">
      <div className="w-full max-w-sm mx-auto p-8 rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] shadow-lg text-center">
        <div className="mb-6">
          <span className="text-2xl font-bold">
            <span className="text-orange-500">Agentic</span>{" "}
            <span className="text-blue-500">KB</span>
          </span>
        </div>
        <p className="text-sm text-[var(--foreground)]/60 mb-8">
          Sign in with your Google account to continue.
        </p>
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}
        <button
          onClick={onSignIn}
          className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white border border-gray-200 text-gray-700 font-medium hover:bg-gray-50 transition-colors shadow-sm cursor-pointer"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg>
          Sign in with Google
        </button>
      </div>
    </div>
  );
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [firebaseReady, setFirebaseReady] = useState(false);
  const authRef = useRef<Auth | null>(null);
  const allowedRef = useRef<string[]>([]);

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;

    (async () => {
      const config = await getRuntimeConfig();
      const allowedEmails = config.allowedEmails
        .split(",").map((e: string) => e.trim().toLowerCase()).filter(Boolean);
      allowedRef.current = allowedEmails;

      const firebaseAuth = await initFirebase();
      if (!firebaseAuth) {
        setUser({
          displayName: "Demo User",
          email: "demo@local",
          photoURL: "https://api.dicebear.com/7.x/bottts/svg?seed=kb-agent"
        } as any);
        setLoading(false);
        return;
      }

      authRef.current = firebaseAuth;
      setFirebaseReady(true);

      unsubscribe = onAuthStateChanged(firebaseAuth, (currentUser) => {
        if (currentUser && allowedEmails.length > 0) {
          const email = (currentUser.email || "").toLowerCase();
          if (!allowedEmails.includes(email)) {
            signOut(firebaseAuth);
            setError(`Access denied for ${currentUser.email}`);
            setUser(null);
            setLoading(false);
            return;
          }
        }
        setError(null);
        setUser(currentUser);
        setLoading(false);
      });
    })();

    return () => unsubscribe?.();
  }, []);

  const signIn = async () => {
    if (!authRef.current) return;
    setError(null);
    const provider = new GoogleAuthProvider();
    await signInWithPopup(authRef.current, provider);
  };

  const logOut = async () => {
    if (!authRef.current) return;
    await signOut(authRef.current);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--background)]">
        <div className="animate-pulse text-[var(--foreground)]/40 text-lg">Loading...</div>
      </div>
    );
  }

  if (firebaseReady && !user) {
    return <LoginScreen onSignIn={signIn} error={error} />;
  }

  return (
    <AuthContext.Provider value={{ user, loading, signIn, logOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
