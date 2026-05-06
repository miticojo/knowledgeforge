"use client";

import { useEffect, useState } from "react";

const DISMISS_KEY = "kf-demo-banner-dismissed";

export function DemoModeBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Honor session-scoped dismissal
    try {
      if (typeof window !== "undefined" && sessionStorage.getItem(DISMISS_KEY) === "1") {
        return;
      }
    } catch {
      // sessionStorage may be unavailable; continue
    }

    // Build-time override
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
      setVisible(true);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && data?.demo_mode === true) {
          setVisible(true);
        }
      } catch {
        // silent: no banner if health check fails
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!visible) return null;

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore
    }
    setVisible(false);
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed top-0 left-0 right-0 z-[100] bg-amber-300 text-amber-950 border-b border-amber-500 shadow-sm"
      data-testid="demo-mode-banner"
    >
      <div className="container mx-auto flex items-center gap-3 px-4 py-2 text-xs sm:text-sm">
        <span className="flex-1 leading-snug">
          <span aria-hidden="true">🧪</span>{" "}
          <strong className="font-semibold">Demo mode</strong> — graph resets when the demo stack restarts. See{" "}
          <a
            href="https://github.com/miticojo-labs/knowledgeforge/blob/main/demo/README.md"
            target="_blank"
            rel="noreferrer noopener"
            className="underline font-medium hover:text-amber-900"
          >
            demo guide
          </a>
          .
        </span>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss demo mode banner"
          className="shrink-0 rounded-md border border-amber-600/40 bg-amber-200/60 px-2 py-0.5 text-xs font-medium hover:bg-amber-100 transition-colors"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

export default DemoModeBanner;
