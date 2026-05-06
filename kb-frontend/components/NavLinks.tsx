"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Database, Search, FlaskConical, LogOut, Network, Sparkles } from "lucide-react";
import { useAuth } from "@/components/providers/AuthProvider";

const links = [
  { href: "/architecture", label: "Architecture", icon: Network, color: "blue" },
  { href: "/ingestion", label: "Fase 1: Ingestion", icon: Database, color: "blue" },
  { href: "/graph", label: "Graph", icon: Network, color: "blue" },
  { href: "/embeddings", label: "Embeddings", icon: Sparkles, color: "blue" },
  { href: "/chat", label: "Fase 2: Search", icon: Search, color: "orange" },
  { href: "/benchmark", label: "Benchmark", icon: FlaskConical, color: "orange" },
  { href: "/dashboard", label: "Dashboard", icon: FlaskConical, color: "orange" },
] as const;

export function NavLinks() {
  const pathname = usePathname();
  const { user, logOut } = useAuth();

  return (
    <nav className="flex items-center gap-1 text-sm font-medium flex-1">
      {links.map(({ href, label, icon: Icon, color }) => {
        const isActive = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg transition-all ${
              isActive
                ? color === "blue"
                  ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                  : "bg-orange-500/10 text-orange-400 border border-orange-500/20"
                : "hover:bg-white/5 text-[var(--foreground)]/70 border border-transparent"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        );
      })}
      {user && (
        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs text-[var(--foreground)]/50">{user.email}</span>
          <button
            onClick={logOut}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[var(--foreground)]/50 hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer"
            title="Sign out"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </nav>
  );
}
