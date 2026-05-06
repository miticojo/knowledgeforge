"use client";

import * as React from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import { lookupGlossary } from "@/lib/glossary";

export interface GlossaryTooltipProps {
  term: string;
  children: React.ReactNode;
}

/**
 * Wraps an inline term with a Radix UI tooltip that exposes its glossary
 * definition on hover/focus. If the term is not in the glossary, children are
 * rendered as plain text (no underline, no popover, no error).
 */
export function GlossaryTooltip({ term, children }: GlossaryTooltipProps) {
  const entry = lookupGlossary(term);
  if (!entry) return <>{children}</>;

  return (
    <Tooltip.Provider delayDuration={150} skipDelayDuration={300}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            tabIndex={0}
            className="cursor-help underline decoration-dotted decoration-cyan-400/60 underline-offset-4 hover:decoration-cyan-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 focus-visible:rounded-sm"
            aria-describedby={`glossary-${entry.term}`}
          >
            {children}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            id={`glossary-${entry.term}`}
            sideOffset={6}
            collisionPadding={12}
            className="z-50 max-w-xs rounded-xl border border-slate-700/80 bg-slate-950/95 px-4 py-3 text-xs leading-relaxed text-slate-200 shadow-2xl backdrop-blur-md data-[state=delayed-open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=delayed-open]:fade-in-0"
          >
            <div className="mb-1 font-mono text-[11px] font-bold uppercase tracking-wider text-cyan-400">
              {entry.term}
            </div>
            <p className="text-slate-300">{entry.definition}</p>
            {entry.link && (
              <a
                href={entry.link}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block text-[11px] font-semibold text-cyan-400 hover:text-cyan-300"
              >
                Learn more →
              </a>
            )}
            <Tooltip.Arrow className="fill-slate-700" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

export default GlossaryTooltip;
