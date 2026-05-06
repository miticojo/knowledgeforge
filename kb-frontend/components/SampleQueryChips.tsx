"use client";

import { Sparkles } from "lucide-react";

export const SAMPLE_QUERIES: readonly string[] = [
  "What components are in this system?",
  "Show the knowledge brief",
  "Impact analysis: what depends on the database?",
  "Most connected entities (god nodes)",
  "How does the auth flow work?",
  "List all DataObjects with their owners",
];

export interface SampleQueryChipsProps {
  onSelect: (query: string) => void;
  disabled?: boolean;
}

export function SampleQueryChips({ onSelect, disabled = false }: SampleQueryChipsProps) {
  return (
    <div
      className="flex flex-wrap gap-2 px-2 pb-2"
      role="group"
      aria-label="Sample queries"
      data-testid="sample-query-chips"
    >
      {SAMPLE_QUERIES.map((q) => (
        <button
          key={q}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(q)}
          className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium transition-all duration-200 ${
            disabled
              ? "opacity-40 cursor-not-allowed border-[var(--card-border)]"
              : "border-orange-500/20 bg-orange-500/5 text-[var(--foreground)]/80 hover:border-orange-500/50 hover:bg-orange-500/10 hover:text-orange-500 active:scale-[0.97]"
          }`}
        >
          <Sparkles className="w-3 h-3 opacity-60 group-hover:opacity-100" />
          <span>{q}</span>
        </button>
      ))}
    </div>
  );
}

export default SampleQueryChips;
