"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";

/**
 * Standalone /login page.
 *
 * AuthProvider already renders an inline LoginScreen when Firebase is enabled
 * and no user is authenticated, so visitors who reach this URL while signed
 * out will see that screen. If they're already signed in, redirect to /.
 *
 * In demo mode (Firebase env vars unset) AuthProvider auto-injects a demo
 * user; this page redirects immediately.
 */
export default function LoginPage() {
  const router = useRouter();
  const { user, signIn } = useAuth();

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-sm p-8 rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] text-center">
        <h1 className="text-xl font-bold mb-4">Sign in to KnowledgeForge</h1>
        <p className="text-sm text-[var(--foreground)]/60 mb-6">
          Use your Google account to access your tenant&apos;s knowledge base.
        </p>
        <button
          onClick={() => signIn()}
          className="w-full px-4 py-3 rounded-xl bg-blue-500 text-white font-medium hover:bg-blue-600 transition-colors"
        >
          Sign in with Google
        </button>
      </div>
    </div>
  );
}
