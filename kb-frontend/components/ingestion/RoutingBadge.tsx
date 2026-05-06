"use client";

import { ReactElement } from "react";

export interface RoutingBadgeProps {
  parser: string;
  reason?: string;
}

type Family = "python" | "tree-sitter" | "gemini" | "sqlglot" | "generic";

function classifyParser(parser: string): Family {
  const p = parser.toLowerCase();
  if (p === "python-ast" || p.startsWith("python-")) return "python";
  if (p.startsWith("tree-sitter")) return "tree-sitter";
  if (p.startsWith("gemini")) return "gemini";
  if (p === "sqlglot" || p.startsWith("sqlglot")) return "sqlglot";
  return "generic";
}

const FAMILY_STYLES: Record<Family, string> = {
  python: "bg-blue-500/15 text-blue-300 border-blue-400/40",
  "tree-sitter": "bg-blue-500/15 text-blue-300 border-blue-400/40",
  gemini: "bg-orange-500/15 text-orange-300 border-orange-400/40",
  sqlglot: "bg-emerald-500/15 text-emerald-300 border-emerald-400/40",
  generic: "bg-white/10 text-white/60 border-white/15",
};

export default function RoutingBadge({ parser, reason }: RoutingBadgeProps): ReactElement {
  const family = classifyParser(parser || "generic");
  return (
    <span
      title={reason ? `${parser} — ${reason}` : parser}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-mono font-semibold uppercase tracking-wide ${FAMILY_STYLES[family]}`}
    >
      {parser || "unrouted"}
    </span>
  );
}
