import type { ReactNode } from "react";

export interface EmptyStateCta {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  body: string;
  cta?: EmptyStateCta;
}

export default function EmptyState({ icon, title, body, cta }: EmptyStateProps) {
  const ctaClassName =
    "inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white text-sm font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-orange-500/20";

  return (
    <div className="flex w-full items-center justify-center p-8">
      <div className="w-full max-w-md text-center space-y-5 rounded-2xl border border-[var(--card-border)] bg-slate-950/60 backdrop-blur-xl p-10 shadow-xl">
        <div className="flex justify-center">
          <div className="relative">
            <div className="absolute inset-0 bg-orange-500/20 blur-2xl rounded-full" />
            <div className="relative flex items-center justify-center w-16 h-16 rounded-2xl bg-orange-500/10 border border-orange-500/20 text-orange-400 [&>svg]:w-8 [&>svg]:h-8">
              {icon}
            </div>
          </div>
        </div>
        <h2 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-orange-400 to-amber-400 bg-clip-text text-transparent">
          {title}
        </h2>
        <p className="text-sm leading-relaxed text-slate-200/80">{body}</p>
        {cta && (
          cta.href ? (
            <a href={cta.href} className={ctaClassName}>
              {cta.label}
            </a>
          ) : (
            <button type="button" onClick={cta.onClick} className={ctaClassName}>
              {cta.label}
            </button>
          )
        )}
      </div>
    </div>
  );
}
