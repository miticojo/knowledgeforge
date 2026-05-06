"use client";

import { AlertCircle, CheckCircle2, FileCode, Loader2 } from "lucide-react";
import RoutingBadge from "./RoutingBadge";

export interface FileTreeRow {
  file: string;
  parser: string;
  status: "routed" | "parsing" | "done" | "failed";
  entities_added: number;
  edges_added: number;
}

export interface FileTreeProps {
  files: FileTreeRow[];
  selected: string | null;
  onSelect: (file: string) => void;
}

function StatusIcon({ status }: { status: FileTreeRow["status"] }) {
  if (status === "failed") return <AlertCircle className="h-3.5 w-3.5 text-red-400" />;
  if (status === "parsing") return <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />;
  if (status === "done") return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />;
  return <FileCode className="h-3.5 w-3.5 text-white/40" />;
}

export default function FileTree({ files, selected, onSelect }: FileTreeProps) {
  if (files.length === 0) {
    return (
      <div
        role="status"
        className="flex h-full min-h-[120px] items-center justify-center text-[11px] text-white/40"
      >
        Awaiting first file…
      </div>
    );
  }

  return (
    <ul
      role="listbox"
      aria-label="Ingested files"
      className="flex h-full min-h-0 flex-col overflow-y-auto"
    >
      {files.map((f) => {
        const active = f.file === selected;
        return (
          <li
            key={f.file}
            role="option"
            aria-selected={active}
            data-active={active ? "true" : undefined}
            onClick={() => onSelect(f.file)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(f.file);
              }
            }}
            tabIndex={0}
            className={`group cursor-pointer border-l-2 px-3 py-2 text-[11px] outline-none transition-colors ${
              active
                ? "border-orange-400 bg-orange-500/10"
                : "border-transparent hover:bg-white/[0.04]"
            }`}
          >
            <div className="flex items-center gap-2">
              <StatusIcon status={f.status} />
              <span
                className="truncate font-mono text-white/85"
                title={f.file}
              >
                {f.file.split("/").pop()}
              </span>
              <RoutingBadge parser={f.parser} />
            </div>
            <div className="ml-5 mt-1 flex items-center gap-2 text-[10px] text-white/45">
              <span className="font-mono">{f.entities_added} ent</span>
              <span className="font-mono">{f.edges_added} edg</span>
              <span
                className="ml-auto truncate font-mono text-white/30"
                title={f.file}
              >
                {f.file}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
