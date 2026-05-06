"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { CopilotChat, AssistantMessage as CopilotAssistantMessage, Markdown } from "@copilotkit/react-ui";
import type { AssistantMessageProps } from "@copilotkit/react-ui";
import { useCopilotChat, useCopilotAction } from "@copilotkit/react-core";
import { LogIn, LogOut, Loader2, Sparkles, Building2, Search, Network, Database, FileText, MessageSquare, Zap, FlaskConical, Upload, Globe, User, Share2 } from "lucide-react";
import { TextMessage, Role } from "@copilotkit/runtime-client-gql";
import { SourcesBox, parseSourcesFromContent } from "@/components/SourcesBox";
import { BenchmarkPanel } from "@/components/BenchmarkPanel";
import { TenantStats } from "@/components/TenantStats";
import { SampleQueryChips } from "@/components/SampleQueryChips";
import { useSearchScope } from "@/components/providers/SearchScopeProvider";
import { EntityScopeBanner } from "@/components/EntityScopeBanner";
import { useGraphStore } from "@/lib/graph-store";

// Micro-component to safely update React state from within useCopilotAction render callbacks without breaking hook rules
function ActionStatusUpdater({ status, agentName, setActiveSubAgent }: { status: string, agentName: any, setActiveSubAgent: any }) {
  useEffect(() => {
    if (status === "inProgress" || status === "executing") {
      setActiveSubAgent(agentName);
    } else if (status === "complete") {
      // Evita che i messaggi storici resettino lo stato in esecuzione
      setActiveSubAgent((prev: any) => prev === agentName ? null : prev);
    }
  }, [status, agentName, setActiveSubAgent]);
  return null;
}

function CustomAssistantMessage(props: AssistantMessageProps) {
  const content = props.message?.content || "";
  const { cleanContent, sources } = parseSourcesFromContent(content);

  // Replace [IMAGE:img_N:doc_id:chunk_id] tags with <img> elements
  // CopilotKit's Markdown uses rehype-raw, so raw HTML renders correctly
  const contentWithImages = cleanContent.replace(
    /\[IMAGE:(img_\d+):([a-f0-9-]+):([a-f0-9-]+)\]/g,
    (_match, imgId, docId, chunkId) => {
      const imgMeta = sources?.images?.find((i) => i.image_id === imgId);
      const alt = imgMeta
        ? `${imgMeta.source_doc} - Page ${imgMeta.page_number ?? "?"}`
        : `Image ${imgId}`;
      return `<img src="/api/image/${docId}/${chunkId}" alt="${alt}" style="max-width:100%;border-radius:8px;margin:8px 0" />`;
    }
  );

  // Create a shallow copy of the message with cleaned content (no <sources> block)
  const cleanMessage = props.message
    ? { ...props.message, content: contentWithImages }
    : props.message;

  return (
    <>
      <CopilotAssistantMessage {...props} message={cleanMessage} />
      {sources && !props.isLoading && !props.isGenerating && (
        <SourcesBox sources={sources} />
      )}
    </>
  );
}

const ARCHISURANCE_EXAMPLES = [
  {
    label: "Oracle dependencies",
    query: "Which applications and business processes depend on Oracle Database? Use graph traversal to find indirect dependencies at 2-3 hops as well.",
    icon: Search, color: "green",
  },
  {
    label: "Cross-document discovery",
    query: "Find all entities connected to the CRM System through the Knowledge Graph, including those documented in other PDFs.",
    icon: Search, color: "green",
  },
  {
    label: "Requirements and constraints",
    query: "Which Requirements and Constraints exist in the Knowledge Graph? How are they linked to strategic Goals and ApplicationComponents?",
    icon: Search, color: "green",
  },
  {
    label: "Impact analysis",
    query: "If we had to shut down the App-Server-PRD-01 server, which ApplicationComponents, BusinessProcesses, and teams would be affected? Generate a report.",
    icon: FileText, color: "blue",
  },
  {
    label: "Full architecture report",
    query: "Generate an architecture report covering all ApplicationComponents, Serving relations to BusinessProcesses, Assignments with BusinessActors, and technology dependencies.",
    icon: FileText, color: "blue",
  },
];

const HOTPOTQA_EXAMPLES = [
  {
    label: "Film & actors",
    query: "What nationality was Oliver Reed's character in the film Royal Flash?",
    icon: Search, color: "purple",
  },
  {
    label: "Music & bands",
    query: "Who released the song \"With or Without You\" first, Jai McDowall or U2?",
    icon: Search, color: "purple",
  },
  {
    label: "Composers & works",
    query: "Pacific Mozart Ensemble performed which German composer's Der Lindberghflug in 2?",
    icon: Search, color: "purple",
  },
  {
    label: "Geography & history",
    query: "What Kentucky county has a population of 60,316 and features the Lake Louisvilla neighborhood?",
    icon: Search, color: "purple",
  },
  {
    label: "Politics & regions",
    query: "Para Hills West, South Australia lies within a city with what estimated population?",
    icon: Search, color: "purple",
  },
];

const SCOPE_OPTIONS = [
  { value: "all" as const, label: "All", icon: Globe },
  { value: "mine" as const, label: "My Data", icon: User },
  { value: "shared" as const, label: "Shared", icon: Share2 },
];

const DATASET_OPTIONS = [
  { value: "archisurance", label: "ArchiSurance", detail: "enterprise architecture", icon: Building2, color: "orange" },
  { value: "hotpotqa", label: "HotpotQA", detail: "academic benchmark", icon: FlaskConical, color: "purple" },
];

function SearchScopeToggle() {
  const { scope, setScope, datasets, toggleDataset } = useSearchScope();
  const showDatasets = scope === "all" || scope === "shared";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1 p-1 rounded-xl bg-black/5 dark:bg-white/5 border border-[var(--card-border)]">
        {SCOPE_OPTIONS.map((opt) => {
          const active = scope === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setScope(opt.value)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-semibold transition-all cursor-pointer ${
                active
                  ? "bg-orange-500/15 text-orange-400 border border-orange-500/30 shadow-sm"
                  : "text-[var(--foreground)]/40 hover:text-[var(--foreground)]/60 border border-transparent"
              }`}
            >
              <opt.icon className="w-3 h-3" />
              {opt.label}
            </button>
          );
        })}
      </div>

      {showDatasets && (
        <div className="flex items-center gap-3 pl-1">
          {DATASET_OPTIONS.map((ds) => {
            const checked = datasets.includes(ds.value);
            const colorClasses = ds.color === "orange"
              ? "text-orange-400"
              : "text-purple-400";
            return (
              <label
                key={ds.value}
                className="flex items-center gap-1.5 cursor-pointer select-none group"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleDataset(ds.value)}
                  className="sr-only peer"
                />
                <span className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-all ${
                  checked
                    ? `${ds.color === "orange" ? "bg-orange-500/20 border-orange-500/40" : "bg-purple-500/20 border-purple-500/40"}`
                    : "border-[var(--card-border)] bg-black/5 dark:bg-white/5"
                }`}>
                  {checked && (
                    <svg className={`w-2.5 h-2.5 ${colorClasses}`} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M2 6l3 3 5-5" />
                    </svg>
                  )}
                </span>
                <ds.icon className={`w-3 h-3 ${checked ? colorClasses : "opacity-30"} transition-all`} />
                <span className={`text-[10px] font-medium transition-all ${
                  checked ? "text-[var(--foreground)]/70" : "text-[var(--foreground)]/30 line-through"
                }`}>
                  {ds.label}
                </span>
                <span className={`text-[9px] opacity-30 hidden xl:inline`}>
                  {ds.detail}
                </span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ExampleQueries({ isLoading, onSend }: { isLoading: boolean; onSend: (q: string) => void }) {
  const [tab, setTab] = useState<"archisurance" | "hotpotqa">("archisurance");
  const examples = tab === "archisurance" ? ARCHISURANCE_EXAMPLES : HOTPOTQA_EXAMPLES;

  return (
    <div className="border-t border-[var(--card-border)] bg-black/5 dark:bg-white/5 flex flex-col overflow-y-auto max-h-[45%]">
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-4 pt-3 pb-1">
        <h3 className="text-[10px] font-bold uppercase tracking-widest opacity-50 flex items-center gap-1.5 mr-auto">
          <Zap className="w-3 h-3" /> Sample queries
        </h3>
        <button
          onClick={() => setTab("archisurance")}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-all ${
            tab === "archisurance"
              ? "bg-orange-500/15 text-orange-400 border border-orange-500/30"
              : "text-white/40 hover:text-white/60 border border-transparent"
          }`}
        >
          <Building2 className="w-3 h-3" /> ArchiSurance
        </button>
        <button
          onClick={() => setTab("hotpotqa")}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-all ${
            tab === "hotpotqa"
              ? "bg-purple-500/15 text-purple-400 border border-purple-500/30"
              : "text-white/40 hover:text-white/60 border border-transparent"
          }`}
        >
          <FlaskConical className="w-3 h-3" /> HotpotQA
        </button>
      </div>

      {/* Dataset badge */}
      <div className="px-4 pb-2">
        <span className={`text-[9px] font-mono opacity-40 ${tab === "archisurance" ? "text-orange-400" : "text-purple-400"}`}>
          {tab === "archisurance"
            ? "Synthetic dataset · 17 docs · ArchiMate enterprise architecture"
            : "Academic benchmark · 1989 docs · Wikipedia multi-hop QA"}
        </span>
      </div>

      {/* Query list */}
      <div className="flex flex-col gap-2 px-4 pb-4">
        {examples.map((ex) => (
          <button
            key={ex.label}
            disabled={isLoading}
            onClick={() => onSend(ex.query)}
            className={`group w-full text-left p-3 rounded-xl border transition-all duration-200 ${
              isLoading
                ? "opacity-40 cursor-not-allowed border-transparent"
                : ex.color === "green"
                ? "border-green-500/10 hover:border-green-500/30 hover:bg-green-500/5 active:scale-[0.98]"
                : ex.color === "blue"
                ? "border-blue-500/10 hover:border-blue-500/30 hover:bg-blue-500/5 active:scale-[0.98]"
                : "border-purple-500/10 hover:border-purple-500/30 hover:bg-purple-500/5 active:scale-[0.98]"
            }`}
          >
            <div className="flex items-start gap-2.5">
              <ex.icon className={`w-4 h-4 mt-0.5 shrink-0 ${
                ex.color === "green" ? "text-green-500" : ex.color === "blue" ? "text-blue-500" : "text-purple-500"
              }`} />
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="text-xs font-semibold text-[var(--foreground)]">{ex.label}</span>
                <span className="text-[10px] opacity-50 line-clamp-2">{ex.query}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Home() {
  const { user, loading, signIn, logOut } = useAuth();
  const searchParams = useSearchParams();
  const promptParam = searchParams?.get("prompt") ?? null;
  const scopeParam = searchParams?.get("scope") ?? null;
  const scope = useGraphStore((s) => s.scope);
  const setScope = useGraphStore((s) => s.setScope);

  // Sync ?scope=id1,id2,... query param into the graph-store so backend search
  // is restricted to those entity ids via X-Entity-Scope header. When no
  // ?scope= is present, clear any previously pinned scope so a stale selection
  // from a prior /graph session does not silently filter all chat results.
  useEffect(() => {
    if (!scopeParam) {
      setScope([]);
      return;
    }
    const ids = scopeParam.split(",").map((s) => s.trim()).filter(Boolean);
    setScope(ids);
  }, [scopeParam, setScope]);

  // Track which subagent is currently executing
  const [activeSubAgent, setActiveSubAgent] = useState<"DocAgent" | null>(null);

  const [hasInteracted, setHasInteracted] = useState(false);
  const [rightWidth, setRightWidth] = useState(380);

  // Pre-fill the CopilotChat textarea when ?prompt= is present.
  // We don't auto-submit — just populate the input so the user can review and send.
  useEffect(() => {
    if (!promptParam || !user) return;
    let attempts = 0;
    const maxAttempts = 50; // ~5s with a 100ms cadence
    const interval = window.setInterval(() => {
      attempts += 1;
      const textarea = document.querySelector<HTMLTextAreaElement>(
        ".copilotKitInput textarea, textarea.copilotKitInput, textarea[placeholder]"
      );
      if (textarea) {
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          "value"
        )?.set;
        setter?.call(textarea, promptParam);
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        textarea.focus();
        window.clearInterval(interval);
      } else if (attempts >= maxAttempts) {
        window.clearInterval(interval);
      }
    }, 100);
    return () => window.clearInterval(interval);
  }, [promptParam, user]);

  const handleMouseDown = (e: React.MouseEvent) => {
    const startX = e.clientX;
    const startWidth = rightWidth;
    const onMouseMove = (moveEvent: MouseEvent) => {
      setRightWidth(Math.max(280, Math.min(600, startWidth - (moveEvent.clientX - startX))));
    };
    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  };

  // Track if CopilotKit is generating overall
  const { isLoading, appendMessage } = useCopilotChat();

  // Derived state for the UI
  const activeAgent = activeSubAgent || (isLoading ? "Coordinator" : "idle");

  useCopilotAction({
    name: "DocAgent",
    description: "Generates structured Markdown documentation based on extracted results.",
    available: "disabled",
    parameters: [
      { name: "message", type: "string" }
    ],
    render: ({ status, args }) => {
      const docPayload = (args as Record<string, any>)?.message || "Autogeneration...";

      return (
        <>
          <ActionStatusUpdater status={status} agentName="DocAgent" setActiveSubAgent={setActiveSubAgent} />
          {status === "inProgress" || status === "executing" ? (
            <div className="flex items-center gap-3 p-4 my-2 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-600 dark:text-blue-400">
              <Loader2 className="w-5 h-5 animate-spin flex-shrink-0" />
              <div className="flex flex-col pr-2">
                <span className="font-medium text-sm">Delegating report drafting to DocAgent...</span>
                <span className="text-xs opacity-80 italic line-clamp-1">"{docPayload}"</span>
              </div>
            </div>
          ) : status === "complete" ? (
            <div className="flex items-center gap-3 p-4 my-2 bg-purple-500/10 border border-purple-500/20 rounded-xl text-purple-600 dark:text-purple-400">
              <Sparkles className="w-5 h-5 flex-shrink-0" />
              <div className="flex flex-col pr-2">
                <span className="font-medium text-sm">Report drafted by DocAgent.</span>
                <span className="text-xs opacity-80 italic line-clamp-1">"{docPayload}"</span>
              </div>
            </div>
          ) : null}
        </>
      );
    }
  });

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-orange-500" />
      </div>
    );
  }

  if (!user) {
    return (
        <main className="flex min-h-screen flex-col items-center justify-center p-8 text-center bg-[var(--background)]">
        <div className="max-w-md w-full p-8 rounded-3xl bg-[var(--card-bg)] border border-[var(--card-border)] backdrop-blur-xl shadow-2xl relative overflow-hidden transition-colors duration-300">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-32 bg-orange-500/20 blur-[60px] pointer-events-none" />
          
          <div className="w-16 h-16 bg-[var(--background)] rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-sm border border-[var(--card-border)] relative">
            <Building2 className="w-8 h-8 text-orange-500" />
            <Sparkles className="w-4 h-4 text-orange-300 absolute -top-1 -right-1" />
          </div>
          
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-orange-400 to-orange-600 mb-2">
            KB Agent
          </h1>
          <p className="opacity-70 mb-8 font-medium">Log in to unleash the power of ADK Search and Generation</p>
          
            <button
            onClick={signIn}
            className="w-full flex items-center justify-center gap-3 bg-[var(--foreground)] text-[var(--background)] font-semibold px-6 py-3.5 rounded-xl hover:opacity-90 active:scale-[0.98] transition-all group"
          >
            <LogIn className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
            Sign in with Google
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex h-[calc(100vh-3.5rem)] w-full flex-col bg-[var(--background)] overflow-hidden relative transition-colors duration-300">
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-orange-600/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute top-1/2 right-0 w-96 h-96 bg-[var(--primary)] opacity-5 rounded-full blur-[120px] pointer-events-none" />

      {/* Main Container */}
      <div className="flex-1 w-full flex flex-col md:flex-row gap-4 px-4 py-4 h-full overflow-hidden">
        
        {/* Left Side: Chat Interface */}
        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {/* Chat Interface */}
          <div className="flex-1 relative rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl flex flex-col overflow-hidden transition-colors duration-300 min-w-0">
            <div className="flex-1 h-full w-full [&>div]:h-full [&>div]:border-0 [&>div]:bg-transparent">
              <CopilotChat
                labels={{
                  title: "Agent Coordinator",
                  initial: "👋 Welcome to the Knowledge Base. I'm the Coordinator and I can help you retrieve up-to-date information using the Search Agent, or distill complex queries and generate full reports for you with the Doc Agent.\n\nWhat would you like to explore today?"
                }}
                AssistantMessage={CustomAssistantMessage}
              />
            </div>
            {/* Sample query chips, rendered above the chat input area */}
            <div className="border-t border-[var(--card-border)] bg-black/5 dark:bg-white/5 pt-2">
              {scope.length > 0 && <EntityScopeBanner />}
              <SampleQueryChips
                disabled={isLoading}
                onSelect={(query) => {
                  setHasInteracted(true);
                  appendMessage(new TextMessage({ content: query, role: Role.User }));
                }}
              />
            </div>
          </div>
        </div>

        {/* Resizable Divider */}
        <div 
          className="hidden lg:block w-1.5 hover:bg-orange-500/30 cursor-col-resize transition-colors rounded-full"
          onMouseDown={handleMouseDown}
        />

        {/* Right Side: Visual Agent Hierarchy */}
        <div 
          style={{ width: `${rightWidth}px` }}
          className="hidden lg:flex shrink-0 relative rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] backdrop-blur-xl shadow-xl flex-col overflow-y-auto transition-colors duration-300"
        >
          <div className="p-4 border-b border-[var(--card-border)] bg-black/5 dark:bg-white/5 space-y-3 sticky top-0 z-30 backdrop-blur-md">
            <h2 className="font-semibold text-sm opacity-80 flex items-center gap-2">
              <Network className="w-4 h-4" /> Live Multi-Agent Architecture
            </h2>
            <TenantStats />
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-widest opacity-50 shrink-0">
                <Search className="w-3 h-3 inline mr-1" />Scope
              </span>
              <SearchScopeToggle />
            </div>
          </div>
          
          <div className="flex flex-col items-center justify-center p-4 relative min-h-[240px] shrink-0">
            {/* Background elements */}
            <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/5 dark:to-white/5" />
            
            <div className="flex flex-col items-center z-10 w-full relative">
              
              {/* Coordinator Agent Node */}
              <div className={`flex flex-col items-center gap-3 transition-all duration-500 z-20 ${
                activeAgent === "Coordinator" 
                  ? "scale-110 drop-shadow-[0_0_20px_rgba(249,115,22,0.4)]" 
                  : "opacity-80 scale-95"
              }`}>
                <div className={`p-5 rounded-2xl border-2 transition-all duration-300 ${
                  activeAgent === "Coordinator" 
                    ? "bg-gradient-to-br from-orange-400 to-orange-600 border-orange-300 text-white shadow-lg" 
                    : "bg-[var(--background)] border-[var(--card-border)] text-orange-500/50"
                }`}>
                  <Network className={`w-8 h-8 ${activeAgent === "Coordinator" ? "animate-pulse" : ""}`} />
                </div>
                <div className="flex flex-col items-center text-center">
                  <span className="font-bold text-sm text-[var(--foreground)]">Coordinator</span>
                  <span className="text-[10px] opacity-60 font-mono tracking-wider uppercase">Orchestrator LlmAgent</span>
                </div>
              </div>

              {/* Connecting Lines */}
              <div className="flex flex-col items-center w-full my-[-10px] z-10">
                {/* Stem down from Coordinator */}
                <div className={`w-1 h-12 transition-colors duration-500 ${
                  activeAgent === "DocAgent" ? "bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.5)]" : activeAgent === "Coordinator" ? "bg-orange-500/40" : "bg-[var(--card-border)]"
                }`} />
                
                {/* Single arm to DocAgent */}
                <div className="flex w-[200px] justify-center">
                  <div className={`w-px h-10 transition-colors duration-500 ${
                    activeAgent === "DocAgent"
                      ? "bg-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.3)]"
                      : "bg-[var(--card-border)]"
                  }`} />
                </div>
              </div>

              {/* Tools & Sub-Agents Row */}
              <div className="flex w-full justify-center items-start px-2 z-20 mt-2 gap-8">

                {/* Search Tool (direct) */}
                <div className={`flex flex-col items-center gap-3 transition-all duration-500 w-[120px] ${
                  activeAgent === "Coordinator"
                    ? "scale-105 drop-shadow-[0_0_15px_rgba(34,197,94,0.3)]"
                    : "opacity-60 scale-95"
                }`}>
                  <div className={`p-3 rounded-xl border transition-all duration-300 ${
                    activeAgent === "Coordinator"
                      ? "bg-green-500/10 border-green-500/30 text-green-400"
                      : "bg-[var(--background)] border-[var(--card-border)] text-green-500/30"
                  }`}>
                    <Database className="w-5 h-5" />
                  </div>
                  <div className="flex flex-col items-center text-center">
                    <span className="font-medium text-xs text-[var(--foreground)]">Hybrid Search</span>
                    <span className="text-[9px] opacity-50 font-mono">Vector + Graph + SQL</span>
                  </div>
                </div>

                {/* Doc Agent */}
                <div className={`flex flex-col items-center gap-3 transition-all duration-500 w-[120px] ${
                  activeAgent === "DocAgent"
                    ? "scale-110 drop-shadow-[0_0_20px_rgba(59,130,246,0.4)]"
                    : "opacity-60 scale-95"
                }`}>
                  <div className={`p-3 rounded-xl border transition-all duration-300 ${
                    activeAgent === "DocAgent"
                      ? "bg-gradient-to-br from-blue-400 to-blue-600 border-blue-300 text-white shadow-lg"
                      : "bg-[var(--background)] border-[var(--card-border)] text-blue-500/30"
                  }`}>
                    <FileText className={`w-5 h-5 ${activeAgent === "DocAgent" ? "animate-pulse" : ""}`} />
                  </div>
                  <div className="flex flex-col items-center text-center">
                    <span className="font-medium text-xs text-[var(--foreground)]">Doc Agent</span>
                    <span className="text-[9px] opacity-50 font-mono">Report Generation</span>
                  </div>
                </div>

              </div>

            </div>

            {/* Status indicator */}
            {activeAgent !== "idle" && (
              <div className="absolute bottom-6 left-0 right-0 flex justify-center z-30">
                <div className="bg-[var(--background)] border border-[var(--card-border)] px-4 py-2 rounded-full shadow-sm flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full animate-pulse ${
                    activeAgent === "Coordinator" ? "bg-orange-500" : "bg-blue-500"
                  }`} />
                  <span className="text-xs font-medium opacity-80">
                    {activeAgent === "Coordinator" ? "Searching & synthesizing answer..." :
                     "Doc Agent is composing report..."}
                  </span>
                </div>
              </div>
            )}

          </div>

          {/* Sample queries — tabbed by dataset */}
          <ExampleQueries
            isLoading={isLoading}
            onSend={(query) => {
              setHasInteracted(true);
              appendMessage(new TextMessage({ content: query, role: Role.User }));
            }}
          />
        </div>
      </div>
    </main>
  );
}
