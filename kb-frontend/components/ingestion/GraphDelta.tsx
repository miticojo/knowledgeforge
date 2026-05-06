"use client";

import { useMemo } from "react";
import Link from "next/link";
import { ExternalLink, Sparkles } from "lucide-react";
import type { AccumulatedGraph, EntityLite } from "@/lib/use-ingest-events";
import { LAYER_COLORS, Layer } from "@/lib/archimate";

export interface GraphDeltaProps {
  accumulated: AccumulatedGraph;
  width?: number;
  height?: number;
}

// Cheap deterministic hash → grid placement.
function hashId(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = (h * 16777619) >>> 0;
  }
  return h >>> 0;
}

function place(id: string, cols: number, rows: number) {
  const h = hashId(id);
  const x = h % cols;
  const y = Math.floor(h / cols) % rows;
  return { gx: x, gy: y };
}

export default function GraphDelta({
  accumulated,
  width = 480,
  height = 280,
}: GraphDeltaProps) {
  const cols = 12;
  const rows = 8;
  const cellW = width / cols;
  const cellH = height / rows;

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number; ent: EntityLite }>();
    // Resolve grid collisions via small spiral offset.
    const taken = new Set<string>();
    for (const ent of accumulated.entities) {
      let { gx, gy } = place(ent.id, cols, rows);
      let tries = 0;
      while (taken.has(`${gx},${gy}`) && tries < cols * rows) {
        gx = (gx + 1) % cols;
        if (gx === 0) gy = (gy + 1) % rows;
        tries++;
      }
      taken.add(`${gx},${gy}`);
      map.set(ent.id, {
        x: gx * cellW + cellW / 2,
        y: gy * cellH + cellH / 2,
        ent,
      });
    }
    return map;
  }, [accumulated.entities, cellW, cellH]);

  const focusParam = useMemo(
    () => accumulated.entities.slice(0, 30).map((e) => e.id).join(","),
    [accumulated.entities]
  );

  return (
    <section
      aria-label="Graph delta"
      className="flex flex-col rounded-2xl border border-white/10 bg-black/30 p-4"
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <h4 className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-white/70">
          <Sparkles className="h-3.5 w-3.5 text-pink-400" />
          Graph delta — {accumulated.entities.length} nodes /{" "}
          {accumulated.edges.length} edges added in this run
        </h4>
        <Link
          href={`/graph${focusParam ? `?focus=${encodeURIComponent(focusParam)}` : ""}`}
          className="inline-flex items-center gap-1.5 rounded-md border border-pink-400/30 bg-pink-500/10 px-2.5 py-1 text-[10px] font-semibold text-pink-300 hover:bg-pink-500/20"
        >
          <ExternalLink className="h-3 w-3" /> Open in /graph
        </Link>
      </header>

      <svg
        role="img"
        aria-label="Animated graph delta canvas"
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        className="rounded-xl bg-black/40"
      >
        <defs>
          <pattern id="gd-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#gd-grid)" />

        {accumulated.edges.map((edge, i) => {
          const a = positions.get(edge.source);
          const b = positions.get(edge.target);
          if (!a || !b) return null;
          return (
            <line
              key={`${edge.source}-${edge.rel}-${edge.target}-${i}`}
              data-testid="gd-edge"
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="rgba(255,255,255,0.18)"
              strokeWidth={1}
            >
              <animate
                attributeName="stroke-opacity"
                from="0"
                to="0.6"
                dur="320ms"
                fill="freeze"
              />
            </line>
          );
        })}

        {Array.from(positions.values()).map(({ x, y, ent }) => {
          const color = LAYER_COLORS[ent.layer as Layer] ?? "#94a3b8";
          return (
            <g key={ent.id} data-testid="gd-node">
              <circle
                cx={x}
                cy={y}
                r={5}
                fill={color}
                stroke="rgba(0,0,0,0.6)"
                strokeWidth={1}
              >
                <animate
                  attributeName="r"
                  from="0"
                  to="5"
                  dur="280ms"
                  fill="freeze"
                />
                <animate
                  attributeName="fill-opacity"
                  from="0"
                  to="1"
                  dur="280ms"
                  fill="freeze"
                />
              </circle>
              <title>
                {ent.name} ({ent.type})
              </title>
            </g>
          );
        })}
      </svg>
    </section>
  );
}
