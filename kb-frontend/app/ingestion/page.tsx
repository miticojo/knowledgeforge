"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { useCopilotChat } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { TextMessage, Role } from "@copilotkit/runtime-client-gql";
import { LogIn, LogOut, Loader2, Sparkles, Building2, Search, Database, FileText, Network, Combine, Fingerprint, RefreshCcw, ChevronDown, Code, GitFork, Trash2, Upload, FlaskConical, CheckCircle2, AlertCircle } from "lucide-react";
import dynamic from "next/dynamic";
import EmptyState from "@/components/EmptyState";
import AgentTimeline from "@/components/ingestion/AgentTimeline";
import FileTree from "@/components/ingestion/FileTree";
import LiveInspector from "@/components/ingestion/LiveInspector";
import GraphDelta from "@/components/ingestion/GraphDelta";
import { useIngestEvents } from "@/lib/use-ingest-events";

const KnowledgeGraph = dynamic(() => import("@/components/KnowledgeGraph"), { ssr: false });

// Map backend tool names -> UI step names
const TOOL_STEP_MAP: Record<string, string> = {
  extract_metadata: "Metadata",
  process_document: "Processing",
  write_to_spanner: "Spanner",
  pipeline_complete: "Complete",
};
const STEP_ORDER = ["Metadata", "Processing", "Spanner", "Complete"];
const STEP_DELAY_MS = 800; // Reduced — parallel processing is faster

export default function IngestionPage() {
  const { user, loading, signIn, logOut } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeSubAgent, setActiveSubAgent] = useState<string | null>(null);
  const [stepResults, setStepResults] = useState<Record<string, any>>({});
  const [fileContent, setFileContent] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [fileUrl, setFileUrl] = useState<string>("");
  const [isExtractingText, setIsExtractingText] = useState<boolean>(false);
  const [pipelineComplete, setPipelineComplete] = useState(false);
  const [extractedImages, setExtractedImages] = useState<any[]>([]);
  const [centerTab, setCenterTab] = useState<"doc" | "graph" | "images">("doc");
  const [isResetting, setIsResetting] = useState(false);

  // Source-mode tabs: document upload vs. git repo ingestion.
  const [sourceTab, setSourceTab] = useState<"upload" | "git">("upload");
  const [gitRepoUrl, setGitRepoUrl] = useState("");
  const [gitRef, setGitRef] = useState("");
  const [gitInclude, setGitInclude] = useState(
    "**/*.py,**/*.ts,**/*.tsx,**/*.java,**/*.go,**/*.sql"
  );
  const [gitExclude, setGitExclude] = useState(
    "node_modules/**,dist/**,build/**,.git/**,**/__pycache__/**,vendor/**,target/**"
  );
  const [gitError, setGitError] = useState<string | null>(null);
  const [gitSubmitting, setGitSubmitting] = useState(false);
  const [gitJobId, setGitJobId] = useState<string | null>(null);
  const [docJobId, setDocJobId] = useState<string | null>(null);
  const [selectedDocFile, setSelectedDocFile] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Live SSE state for the active git job — single shared subscription used by
  // both AgentTimeline (right column), FileTree, LiveInspector, and GraphDelta.
  const gitState = useIngestEvents(sourceTab === "git" ? gitJobId : null);
  const docState = useIngestEvents(sourceTab === "upload" ? docJobId : null);
  const [selectedGitFile, setSelectedGitFile] = useState<string | null>(null);
  const [showDelta, setShowDelta] = useState(false);

  // Auto-select the most recent parsed file as new ones arrive.
  useEffect(() => {
    if (sourceTab !== "git") return;
    const summaries = gitState.fileSummaries;
    if (summaries.length === 0) {
      setSelectedGitFile(null);
      return;
    }
    if (selectedGitFile && summaries.some((s) => s.file === selectedGitFile)) {
      return;
    }
    // Default to the most recent "done" file, or first parsing/routed.
    const done = [...summaries].reverse().find((s) => s.status === "done");
    setSelectedGitFile((done ?? summaries[summaries.length - 1]).file);
  }, [gitState.fileSummaries, sourceTab, selectedGitFile]);

  // Auto-select the most recent doc file (typically only one).
  useEffect(() => {
    if (sourceTab !== "upload") return;
    const summaries = docState.fileSummaries;
    if (summaries.length === 0) {
      setSelectedDocFile(null);
      return;
    }
    if (selectedDocFile && summaries.some((s) => s.file === selectedDocFile)) {
      return;
    }
    const done = [...summaries].reverse().find((s) => s.status === "done");
    setSelectedDocFile((done ?? summaries[summaries.length - 1]).file);
  }, [docState.fileSummaries, sourceTab, selectedDocFile]);

  const selectedDocFileMeta = selectedDocFile
    ? docState.fileSummaries.find((s) => s.file === selectedDocFile) ?? null
    : null;

  const selectedGitFileMeta = selectedGitFile
    ? gitState.fileSummaries.find((s) => s.file === selectedGitFile) ?? null
    : null;

  const { appendMessage, isLoading } = useCopilotChat();
  const interceptorInstalled = useRef(false);
  const originalFetchRef = useRef<typeof fetch | null>(null);

  const activeAgent = activeSubAgent || (isLoading ? "ProcessingAgent" : "idle");

  // Auto-switch to Knowledge Graph tab when Processing step completes (contains graph data)
  useEffect(() => {
    if (stepResults["Processing"]) {
      setCenterTab("graph");
    }
  }, [stepResults["Processing"]]);

  // SSE Interceptor: cattura TOOL_CALL events dal flusso AG-UI e aggiorna il pipeline state
  const processSSEStream = useCallback(async (response: Response) => {
    const reader = response.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();
    const toolCallNames: Record<string, string> = {};
    // Traccia ordine di arrivo per stagger
    const arrivedSteps: string[] = [];

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        const lines = text.split("\n").filter((l) => l.startsWith("data:"));
        for (const line of lines) {
          try {
            const event = JSON.parse(line.slice(5));

            if (event.type === "TOOL_CALL_START" && event.toolCallName) {
              const stepName = TOOL_STEP_MAP[event.toolCallName];
              if (stepName) {
                toolCallNames[event.toolCallId] = stepName;
                if (!arrivedSteps.includes(stepName)) arrivedSteps.push(stepName);
                const idx = arrivedSteps.indexOf(stepName);
                const delay = idx * STEP_DELAY_MS;
                setTimeout(() => {
                  setActiveSubAgent(stepName);
                }, delay);
              }
            }

            if (event.type === "TOOL_CALL_ARGS" && event.toolCallId) {
              const stepName = toolCallNames[event.toolCallId];
              if (stepName) {
                try {
                  const args = JSON.parse(event.delta);
                  const idx = arrivedSteps.indexOf(stepName);
                  const delay = idx * STEP_DELAY_MS + 200;
                  setTimeout(() => {
                    setStepResults((prev) => ({
                      ...prev,
                      [`${stepName}_args`]: args,
                    }));
                  }, delay);
                } catch {}
              }
            }

            if (event.type === "TOOL_CALL_RESULT" && event.toolCallId) {
              const stepName = toolCallNames[event.toolCallId];
              if (stepName) {
                let resultData: any = event.content;
                try { resultData = JSON.parse(resultData); } catch {}
                if (resultData?.result) {
                  try { resultData = JSON.parse(resultData.result); } catch { resultData = resultData.result; }
                }
                const idx = arrivedSteps.indexOf(stepName);
                const delay = idx * STEP_DELAY_MS + 800;
                setTimeout(() => {
                  setStepResults((prev) => ({ ...prev, [stepName]: resultData }));
                  // Avanza allo step successivo o fine
                  const nextIdx = STEP_ORDER.indexOf(stepName) + 1;
                  if (nextIdx < STEP_ORDER.length && arrivedSteps.includes(STEP_ORDER[nextIdx])) {
                    setActiveSubAgent(STEP_ORDER[nextIdx]);
                  } else if (stepName === "Spanner") {
                    setTimeout(() => {
                      setActiveSubAgent(null);
                      setPipelineComplete(true);
                    }, 600);
                  }
                }, delay);
              }
            }
          } catch {}
        }
      }
    } catch {}
  }, []);

  // Install fetch interceptor
  useEffect(() => {
    if (interceptorInstalled.current) return;
    interceptorInstalled.current = true;
    originalFetchRef.current = window.fetch;
    const origFetch = window.fetch;

    window.fetch = async function (...args: Parameters<typeof fetch>) {
      const response = await origFetch.apply(this, args);
      const url = typeof args[0] === "string" ? args[0] : (args[0] as Request)?.url || "";
      if (url.includes("/api/copilotkit")) {
        const cloned = response.clone();
        processSSEStream(cloned);
      }
      return response;
    };

    return () => {
      if (originalFetchRef.current) {
        window.fetch = originalFetchRef.current;
      }
    };
  }, [processSSEStream]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setFileName(file.name);
    setFileContent("");
    setFileUrl(URL.createObjectURL(file));
    setExtractedImages([]);
    setUploadedFile(file);
    // Reset any prior doc job so the right column falls back to its empty state.
    setDocJobId(null);
    setSelectedDocFile(null);

    if (file.type === "application/pdf" || file.name.endsWith(".pdf") || file.name.endsWith(".docx") || file.name.endsWith(".xlsx") || file.name.endsWith(".pptx")) {
      setIsExtractingText(true);
      try {
        const formData = new FormData();
        formData.append("file", file);

        const res = await fetch("/api/parse", {
          method: "POST",
          headers: { "X-Tenant-Id": user?.email || "" },
          body: formData,
        });
        if (!res.ok) throw new Error("Parse API error (" + res.status + ")");

        const data = await res.json();
        setFileContent(data.text);
        if (data.images?.length > 0) {
          setExtractedImages(data.images);
          setCenterTab("images");
        }
      } catch (err) {
        console.error("Text extraction failed:", err);
        setFileContent("Error while extracting text from the document.");
      } finally {
        setIsExtractingText(false);
      }
    } else {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const text = ev.target?.result;
        if (typeof text === 'string') {
          setFileContent(text);
        }
      };
      reader.readAsText(file);
    }
  };

  const handleProcessClick = async () => {
    if (!fileContent.trim()) return;
    setActiveSubAgent("ProcessingAgent");
    setStepResults({});
    setPipelineComplete(false);

    // 0. Kick off the new event-streamed ingestion in parallel with the legacy
    // CopilotKit flow. The new path drives AgentTimeline + FileTree +
    // LiveInspector; the legacy flow remains as a fallback.
    (async () => {
      try {
        let res: Response;
        if (uploadedFile) {
          const fd = new FormData();
          fd.append("file", uploadedFile);
          res = await fetch("/api/ingest/document", {
            method: "POST",
            headers: { "X-Tenant-Id": user?.email || "" },
            body: fd,
          });
        } else {
          res = await fetch("/api/ingest/document", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Tenant-Id": user?.email || "",
            },
            body: JSON.stringify({
              text: fileContent,
              fileName: fileName,
              images: extractedImages.map((img: any) => ({
                pageNum: img.pageNum,
                dataUri: img.dataUri,
              })),
            }),
          });
        }
        if (res.ok) {
          const data = await res.json().catch(() => ({} as any));
          if (data?.job_id) {
            setDocJobId(String(data.job_id));
            setSelectedDocFile(null);
          }
        }
      } catch {
        // Non-fatal: legacy CopilotKit flow continues regardless.
      }
    })();

    // 1. Upload testo completo al backend per chunking (bypass LLM token limit)
    try {
      await fetch("/api/upload-document", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-Id": user?.email || "",
        },
        body: JSON.stringify({
          text: fileContent,
          fileName: fileName,
          images: extractedImages.map((img: any) => ({
            pageNum: img.pageNum,
            dataUri: img.dataUri,
          })),
        }),
      });
    } catch {}

    // 2. Invia versione troncata al LLM per estrazione semantica
    const truncatedContent = fileContent.length > 15000
      ? fileContent.substring(0, 15000) + "\n\n...[DOCUMENT TRUNCATED - " + fileContent.length + " total characters]"
      : fileContent;

    appendMessage(new TextMessage({
      content: `Start the ingestion of the following document:\n\n${truncatedContent}`,
      role: Role.User
    }));
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);


  const handleGitSubmit = async () => {
    setGitError(null);
    const url = gitRepoUrl.trim();
    if (!url) {
      setGitError("Repository URL is required");
      return;
    }
    // Basic URL shape check: http(s)://, ssh://, git@host:path, or file:// (demo mode)
    const ok = /^(https?:\/\/\S+|git@[^\s:]+:\S+|ssh:\/\/\S+|file:\/\/\S+)$/.test(url);
    if (!ok) {
      setGitError("Enter a valid http(s)://, ssh://, git@host:path, or file:// URL");
      return;
    }

    const splitGlobs = (raw: string) =>
      raw.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);

    setGitSubmitting(true);
    setActiveSubAgent("ProcessingAgent");
    setStepResults({});
    setPipelineComplete(false);
    try {
      const res = await fetch("/api/ingest-git", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-Id": user?.email || "",
        },
        body: JSON.stringify({
          repo_url: url,
          ref: gitRef.trim() || undefined,
          include: splitGlobs(gitInclude),
          exclude: splitGlobs(gitExclude),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setGitError(data?.detail || data?.error || `Request failed (${res.status})`);
        setActiveSubAgent(null);
        return;
      }
      setGitJobId(data.job_id || null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Network error";
      setGitError(message);
      setActiveSubAgent(null);
    } finally {
      setGitSubmitting(false);
    }
  };

  const handleResetGraph = async () => {
    if (!confirm("Do you want to delete ALL data from the Knowledge Graph? This action is irreversible.")) return;
    setIsResetting(true);
    try {
      const res = await fetch("/api/reset-graph", {
        method: "POST",
        headers: { "X-Tenant-Id": user?.email || "" },
      });
      const data = await res.json();
      if (res.ok) {
        alert(`Knowledge Graph cleared successfully.`);
        setStepResults({});
        setPipelineComplete(false);
      } else {
        alert(`Error: ${data.detail || "Reset failed"}`);
      }
    } catch (err: any) {
      alert(`Network error: ${err.message}`);
    } finally {
      setIsResetting(false);
    }
  };

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--background)]">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--foreground)] opacity-50" />
      </main>
    );
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 via-background to-orange-500/10 pointer-events-none" />
        <div className="relative w-full max-w-md text-center space-y-8 p-10 bg-black/40 backdrop-blur-xl border border-white/10 rounded-3xl shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
          <div className="flex justify-center mb-6 relative">
            <div className="absolute inset-0 bg-orange-500 blur-3xl opacity-20 object-cover" />
            <Building2 className="w-16 h-16 text-orange-400 relative z-10 drop-shadow-[0_0_15px_rgba(249,115,22,0.5)]" />
          </div>
          <div className="space-y-3 relative z-10">
            <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-orange-400 to-amber-500 bg-clip-text text-transparent">Knowledge Base</h1>
            <p className="text-sm font-medium text-[var(--foreground)] opacity-80 uppercase tracking-widest">Enterprise Platform</p>
          </div>
          <button
            onClick={signIn}
            className="group relative w-full flex items-center justify-center gap-3 px-8 py-4 bg-white/10 hover:bg-white/20 text-white rounded-2xl font-bold transition-all duration-300 hover:scale-[1.02] border border-white/10 hover:border-white/20 active:scale-95"
          >
            <LogIn className="w-5 h-5 group-hover:-translate-y-0.5 transition-transform" />
            Sign in with Google
            <div className="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-orange-400 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
        </div>
      </main>
    );
  }

  const formatRightSideResult = (raw: any) => {
    if (!raw) return null;
    let obj = raw;
    if (typeof raw === "string" && raw.startsWith("{")) {
       try { obj = JSON.parse(raw); } catch {}
    }

    if (obj && obj.result) {
       if (typeof obj.result === "string" && obj.result.startsWith("{")) {
          try { obj = JSON.parse(obj.result); } catch { obj = obj.result; }
       } else {
          obj = obj.result;
       }
    }

    if (typeof obj === 'object' && obj !== null) {
       return (
         <div className="mt-3 flex flex-col gap-2">
            {Object.entries(obj).map(([key, val]) => (
                <div key={key} className="bg-black/20 rounded-lg p-2 border border-white/5">
                   <span className="text-[10px] uppercase font-bold text-orange-400 opacity-80">{key}</span>
                   <div className="text-xs mt-1 text-[var(--foreground)] leading-relaxed overflow-x-auto">
                      {typeof val === 'object' ? <pre className="whitespace-pre-wrap">{JSON.stringify(val, null, 2)}</pre> : String(val)}
                   </div>
                </div>
            ))}
         </div>
       );
    }

    return (
      <div className="mt-3 bg-black/40 border border-white/10 rounded-xl p-3 overflow-x-auto shadow-inner">
        <pre className="text-[11px] text-orange-200/80 font-mono leading-relaxed whitespace-pre-wrap">{String(obj)}</pre>
      </div>
    );
  };

  return (
    <main className="flex h-[calc(100vh-3.5rem)] relative overflow-hidden bg-[var(--background)]">
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-orange-500/10 rounded-full blur-[120px] pointer-events-none shrink-0" />
      <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-blue-500/10 rounded-full blur-[100px] pointer-events-none shrink-0" />

      {/* COLONNA 1: CARICAMENTO (Upload) */}
      <div className="w-[380px] shrink-0 border-r border-[var(--card-border)] bg-[var(--background)]/80 backdrop-blur z-20 flex flex-col overflow-y-auto">
        <div className="p-5 border-b border-[var(--card-border)] bg-[var(--background)]/50 backdrop-blur-md flex items-center justify-between sticky top-0 z-30">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-orange-400" />
            <h2 className="font-semibold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white to-white/70">Ingestion</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleResetGraph}
              disabled={isResetting}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 hover:text-amber-300 rounded-lg transition-all disabled:opacity-50"
            >
              {isResetting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />} Reset Graph
            </button>
            <button
              onClick={logOut}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-300 rounded-lg transition-all"
            >
              <LogOut className="w-3.5 h-3.5" /> Sign out
            </button>
          </div>
        </div>

        {/* Source Mode Tabs */}
        <div role="tablist" aria-label="Ingestion source" className="px-4 pt-3 pb-0 flex items-end gap-0.5 border-b border-[var(--card-border)] bg-[var(--background)]/60">
          <button
            role="tab"
            aria-selected={sourceTab === "upload"}
            onClick={() => setSourceTab("upload")}
            className={`flex items-center gap-1.5 px-3.5 py-2 text-[11px] font-semibold relative transition-colors ${
              sourceTab === "upload" ? "text-orange-400" : "text-white/40 hover:text-white/70"
            }`}
          >
            <Upload className="w-3.5 h-3.5" /> Upload
            {sourceTab === "upload" && (
              <span className="absolute bottom-0 left-1 right-1 h-[2px] bg-gradient-to-r from-orange-500 to-amber-500 rounded-full" />
            )}
          </button>
          <button
            role="tab"
            aria-selected={sourceTab === "git"}
            onClick={() => setSourceTab("git")}
            className={`flex items-center gap-1.5 px-3.5 py-2 text-[11px] font-semibold relative transition-colors ${
              sourceTab === "git" ? "text-orange-400" : "text-white/40 hover:text-white/70"
            }`}
          >
            <GitFork className="w-3.5 h-3.5" /> Code Repository
            {sourceTab === "git" && (
              <span className="absolute bottom-0 left-1 right-1 h-[2px] bg-gradient-to-r from-orange-500 to-amber-500 rounded-full" />
            )}
          </button>
        </div>

        <div className="p-6 space-y-6">

          {/* Upload Panel */}
          {sourceTab === "upload" && (
            <>
              <div className="bg-orange-500/10 border border-orange-500/20 rounded-xl p-5 text-sm flex flex-col gap-4 shadow-lg shadow-black/10">
                <p className="font-semibold text-orange-400 text-base">Initialize Document Pipeline</p>
                <p className="opacity-90 leading-relaxed text-[var(--foreground)] text-xs">
                  Upload a document (.txt, .pdf, .docx, .xlsx, .pptx) to start extraction.
                  The `ProcessingAgent` will feed this text through a strict sequence of tools to: extract metadata, compute vector embeddings, reconcile entities, and build the Knowledge Graph.
                </p>

                <div className="flex flex-col gap-2 pt-2">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-orange-400/80">
                    Select document file
                  </label>
                  <div className="flex gap-2 items-center bg-black/20 rounded-xl p-1 border border-white/5">
                    <input
                      type="file"
                      accept=".txt,.pdf,.docx,.xlsx,.pptx"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      className="flex-1 block w-full text-xs text-[var(--foreground)]
                        file:mr-3 file:py-2 file:px-4
                        file:rounded-lg file:border-0
                        file:text-xs file:font-semibold
                        file:bg-orange-500/10 file:text-orange-400
                        hover:file:bg-orange-500/20 cursor-pointer"
                    />
                  </div>
                  {isExtractingText && <div className="flex items-center gap-2 mt-2"><Loader2 className="w-3 h-3 animate-spin text-orange-400" /><p className="text-xs text-orange-400">Extracting text...</p></div>}
                  {fileName && !isExtractingText && <p className="text-xs text-green-400 mt-2 font-medium">Uploaded: {fileName} ({fileContent.length} char)</p>}
                </div>

                <div className="pt-2">
                  <button
                    onClick={handleProcessClick}
                    disabled={!fileContent || isLoading || isExtractingText}
                    className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all ${
                      !fileContent || isLoading || isExtractingText ? 'bg-white/5 text-white/40 cursor-not-allowed' : 'bg-orange-500 hover:bg-orange-600 text-white shadow-lg shadow-orange-500/20 hover:scale-[1.01]'
                    }`}
                  >
                    {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                    {isLoading ? 'Processing in progress...' : 'Start Processing'}
                  </button>
                </div>
              </div>

              {isLoading && (
                 <div className="animate-pulse flex items-center justify-center p-6 bg-blue-500/5 border border-blue-500/20 rounded-xl">
                   <div className="flex flex-col items-center gap-3">
                      <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
                      <p className="text-xs font-medium text-blue-300 text-center">
                        The system is processing the pipeline autonomously.
                      </p>
                   </div>
                 </div>
              )}
            </>
          )}

          {/* Code Repository Panel */}
          {sourceTab === "git" && (
            <div
              role="tabpanel"
              aria-label="Code Repository"
              className="bg-orange-500/10 border border-orange-500/20 rounded-xl p-5 text-sm flex flex-col gap-4 shadow-lg shadow-black/10"
            >
              <p className="font-semibold text-orange-400 text-base flex items-center gap-2">
                <GitFork className="w-4 h-4" /> Ingest Source Code Repository
              </p>
              <p className="opacity-90 leading-relaxed text-[var(--foreground)] text-xs">
                Clone a Git repository and project its source files into the Knowledge Graph.
                AST-level entities (modules, classes, functions, imports) are extracted and reconciled across files.
              </p>

              <div className="flex flex-col gap-1.5 pt-1">
                <label htmlFor="git-repo-url" className="text-[10px] font-bold uppercase tracking-wider text-orange-400/80">
                  Repository URL <span className="text-red-400">*</span>
                </label>
                <input
                  id="git-repo-url"
                  type="text"
                  required
                  placeholder="https://github.com/org/repo.git"
                  value={gitRepoUrl}
                  onChange={(e) => setGitRepoUrl(e.target.value)}
                  className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-[var(--foreground)] placeholder:text-white/30 focus:outline-none focus:border-orange-400/60"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="git-ref" className="text-[10px] font-bold uppercase tracking-wider text-orange-400/80">
                  Branch / Ref (optional)
                </label>
                <input
                  id="git-ref"
                  type="text"
                  placeholder="main"
                  value={gitRef}
                  onChange={(e) => setGitRef(e.target.value)}
                  className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-[var(--foreground)] placeholder:text-white/30 focus:outline-none focus:border-orange-400/60"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="git-include" className="text-[10px] font-bold uppercase tracking-wider text-orange-400/80">
                  Include Globs
                </label>
                <textarea
                  id="git-include"
                  rows={2}
                  value={gitInclude}
                  onChange={(e) => setGitInclude(e.target.value)}
                  className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[11px] font-mono text-[var(--foreground)] focus:outline-none focus:border-orange-400/60 resize-none"
                />
                <span className="text-[10px] text-white/40">Comma- or newline-separated</span>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="git-exclude" className="text-[10px] font-bold uppercase tracking-wider text-orange-400/80">
                  Exclude Globs
                </label>
                <textarea
                  id="git-exclude"
                  rows={2}
                  value={gitExclude}
                  onChange={(e) => setGitExclude(e.target.value)}
                  className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[11px] font-mono text-[var(--foreground)] focus:outline-none focus:border-orange-400/60 resize-none"
                />
              </div>

              {gitError && (
                <div role="alert" className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg p-2.5 text-xs text-red-300">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>{gitError}</span>
                </div>
              )}

              {gitJobId && !gitError && (
                <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2.5 text-xs text-emerald-300">
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span>Job queued: <span className="font-mono">{gitJobId}</span></span>
                </div>
              )}

              <div className="pt-1">
                <button
                  type="button"
                  onClick={handleGitSubmit}
                  disabled={gitSubmitting || !gitRepoUrl.trim()}
                  className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all ${
                    gitSubmitting || !gitRepoUrl.trim()
                      ? "bg-white/5 text-white/40 cursor-not-allowed"
                      : "bg-orange-500 hover:bg-orange-600 text-white shadow-lg shadow-orange-500/20 hover:scale-[1.01]"
                  }`}
                >
                  {gitSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitFork className="w-4 h-4" />}
                  {gitSubmitting ? "Queuing job..." : "Ingest Repository"}
                </button>
              </div>
            </div>
          )}

        </div>
      </div>

      {/* COLONNA 2: ANTEPRIME + KNOWLEDGE GRAPH */}
      <div className="flex-1 border-r border-[var(--card-border)] relative z-10 flex flex-col bg-black/10">
        {/* Tab bar */}
        <div className="px-5 pt-4 pb-0 border-b border-[var(--card-border)] bg-[var(--background)]/80 backdrop-blur-md sticky top-0 z-30 flex items-end gap-1">
          <button
            onClick={() => setCenterTab("doc")}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg border border-b-0 transition-all ${
              centerTab === "doc"
                ? "bg-black/20 text-orange-400 border-[var(--card-border)]"
                : "text-white/40 border-transparent hover:text-white/60"
            }`}
          >
            <Code className="w-3.5 h-3.5" /> Document
          </button>
          <button
            onClick={() => setCenterTab("graph")}
            disabled={!stepResults["Processing"]?.graph}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg border border-b-0 transition-all ${
              centerTab === "graph"
                ? "bg-black/20 text-pink-400 border-[var(--card-border)]"
                : stepResults["Processing"]?.graph
                ? "text-white/40 border-transparent hover:text-white/60"
                : "text-white/15 border-transparent cursor-not-allowed"
            }`}
          >
            <GitFork className="w-3.5 h-3.5" /> Knowledge Graph
            {stepResults["Processing"]?.graph && centerTab !== "graph" && (
              <span className="w-2 h-2 rounded-full bg-pink-500 animate-pulse" />
            )}
          </button>
          <button
            onClick={() => setCenterTab("images")}
            disabled={extractedImages.length === 0}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold rounded-t-lg border border-b-0 transition-all ${
              centerTab === "images"
                ? "bg-black/20 text-emerald-400 border-[var(--card-border)]"
                : extractedImages.length > 0
                ? "text-white/40 border-transparent hover:text-white/60"
                : "text-white/15 border-transparent cursor-not-allowed"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" /> Images ({extractedImages.length})
            {extractedImages.length > 0 && centerTab !== "images" && (
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            )}
          </button>
        </div>

        {/* Tab content: Documento — Upload tab with active doc job */}
        {centerTab === "doc" && sourceTab === "upload" && docJobId && (
          <div className="flex-1 flex flex-col relative h-full min-h-0">
            <div className="basis-1/3 min-h-0 border-b border-[var(--card-border)] bg-black/20 flex flex-col">
              <div className="px-4 py-2 border-b border-white/5 flex items-center justify-between">
                <h4 className="text-[11px] font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                  <FileText className="w-3 h-3 text-orange-400" /> Files ({docState.fileSummaries.length})
                </h4>
              </div>
              <div className="flex-1 min-h-0">
                <FileTree
                  files={docState.fileSummaries.map((s) => ({
                    file: s.file,
                    parser: s.parser,
                    status: s.status,
                    entities_added: s.entities,
                    edges_added: s.edges,
                  }))}
                  selected={selectedDocFile}
                  onSelect={setSelectedDocFile}
                />
              </div>
            </div>

            <div className="flex-1 min-h-0 basis-2/3 bg-black/40">
              <LiveInspector
                jobId={docJobId}
                selectedFile={selectedDocFile}
                parser={selectedDocFileMeta?.parser ?? null}
                tenantId={user?.email || ""}
                onClose={() => setSelectedDocFile(null)}
              />
            </div>
          </div>
        )}

        {/* Tab content: Documento — Git tab with active job */}
        {centerTab === "doc" && sourceTab === "git" && gitJobId && (
          <div className="flex-1 flex flex-col relative h-full min-h-0">
            {/* Top half: file tree */}
            <div className="basis-1/3 min-h-0 border-b border-[var(--card-border)] bg-black/20 flex flex-col">
              <div className="px-4 py-2 border-b border-white/5 flex items-center justify-between">
                <h4 className="text-[11px] font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                  <GitFork className="w-3 h-3 text-orange-400"/> Files ({gitState.fileSummaries.length})
                </h4>
              </div>
              <div className="flex-1 min-h-0">
                <FileTree
                  files={gitState.fileSummaries.map((s) => ({
                    file: s.file,
                    parser: s.parser,
                    status: s.status,
                    entities_added: s.entities,
                    edges_added: s.edges,
                  }))}
                  selected={selectedGitFile}
                  onSelect={setSelectedGitFile}
                />
              </div>
            </div>

            {/* Bottom half: live inspector */}
            <div className="flex-1 min-h-0 basis-2/3 bg-black/40">
              <LiveInspector
                jobId={gitJobId}
                selectedFile={selectedGitFile}
                parser={selectedGitFileMeta?.parser ?? null}
                tenantId={user?.email || ""}
                onClose={() => setSelectedGitFile(null)}
              />
            </div>

            {showDelta && (
              <div className="border-t border-[var(--card-border)] bg-black/40 p-3">
                <GraphDelta accumulated={gitState.accumulated} />
              </div>
            )}
          </div>
        )}

        {centerTab === "doc" && !(sourceTab === "git" && gitJobId) && !(sourceTab === "upload" && docJobId) && (
          <div className="flex-1 flex flex-col relative h-full">
            {/* Box 1: File Originale */}
            <div className="flex-1 border-b border-[var(--card-border)] p-4 basis-1/2 overflow-hidden flex flex-col bg-black/20">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                <Sparkles className="w-3 h-3 text-orange-400"/> Original File Preview
              </h4>
              {fileUrl ? (
                <iframe src={fileUrl} className="w-full flex-1 rounded-xl border border-white/10 bg-white" />
              ) : (
                <div className="flex-1 flex items-center justify-center text-gray-600 text-sm border-2 border-dashed border-white/5 rounded-xl">
                  No file uploaded
                </div>
              )}
            </div>

            {/* Box 2: JSON / Testo LiteParse */}
            <div className="flex-1 p-4 basis-1/2 overflow-y-scroll flex flex-col bg-black/40">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                <FileText className="w-3 h-3 text-emerald-400"/> Extracted Text (LiteParse)
              </h4>
              {isExtractingText ? (
                <div className="flex-1 flex flex-col items-center justify-center gap-3 text-sm text-gray-400 animate-pulse">
                  <Loader2 className="w-8 h-8 animate-spin text-emerald-400"/>
                  Analyzing and parsing...
                </div>
              ) : fileContent ? (
                <pre className="text-[11px] leading-relaxed text-gray-300 font-mono bg-[#0a0a0a] p-4 border border-white/5 shadow-inner rounded-xl whitespace-pre-wrap">
                  {fileContent}
                </pre>
              ) : (
                <div className="flex-1 flex items-center justify-center text-gray-600 text-sm border-2 border-dashed border-white/5 rounded-xl">
                  Waiting for parsing...
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab content: Knowledge Graph */}
        {centerTab === "graph" && stepResults["Processing"]?.graph && (
          <div className="flex-1 flex flex-col bg-[#0a0a0a] relative min-h-0">
            <KnowledgeGraph graphData={stepResults["Processing"]?.graph} />
          </div>
        )}

        {/* Tab content: Immagini Estratte */}
        {centerTab === "images" && (
          <div className="flex-1 flex flex-col bg-black/20 overflow-y-auto p-6">
            {extractedImages.length === 0 ? (
              <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
                No images detected in the document
              </div>
            ) : (
              <div className="space-y-6">
                <div className="flex items-center gap-3">
                  <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5">
                    <span className="text-xs font-bold text-emerald-400">{extractedImages.length} images detected</span>
                  </div>
                  <span className="text-[10px] text-white/40">Extracted via PDFium by LiteParse &middot; ready for multimodal Gemini Embeddings</span>
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {extractedImages.map((img, idx) => (
                    <div key={idx} className="bg-black/40 border border-white/10 rounded-xl overflow-hidden group hover:border-emerald-500/30 transition-all">
                      <div className="relative">
                        <img
                          src={img.dataUri}
                          alt={`Image ${idx + 1} - Page ${img.pageNum}`}
                          className="w-full h-auto"
                          style={{
                            clipPath: `inset(${(img.bounds.y / img.pageHeight) * 100}% ${100 - ((img.bounds.x + img.bounds.width) / img.pageWidth) * 100}% ${100 - ((img.bounds.y + img.bounds.height) / img.pageHeight) * 100}% ${(img.bounds.x / img.pageWidth) * 100}%)`,
                          }}
                        />
                        <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm px-2 py-1 rounded-md">
                          <span className="text-[9px] font-mono text-emerald-400">Page {img.pageNum}</span>
                        </div>
                      </div>
                      <div className="p-3 border-t border-white/5 flex items-center justify-between">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-[10px] font-bold text-white/70">Image {idx + 1}</span>
                          <span className="text-[9px] text-white/30 font-mono">{img.bounds.width}x{img.bounds.height}px @ ({img.bounds.x}, {img.bounds.y})</span>
                        </div>
                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-md px-2 py-0.5">
                          <span className="text-[9px] font-semibold text-emerald-400">Embedding Ready</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* CopilotChat nascosta ma renderizzata per mantenere il funzionamento degli hook */}
        <div className="opacity-0 w-px h-px overflow-hidden pointer-events-none fixed -bottom-10">
          <CopilotChat
            className="copilot-theme"
            labels={{
              title: "Agent Execution Log",
              initial: "Waiting for a document to start multimodal ingestion...",
            }}
          />
        </div>
      </div>

      {/* COLONNA 3: STEPS DI PROCESSO (Live Ingestion Pipeline) */}
      <div className="hidden lg:flex w-[480px] bg-[var(--background)]/80 backdrop-blur flex-col relative z-20 overflow-hidden">
        {sourceTab === "git" && gitJobId ? (
          <div className="flex flex-1 min-h-0 flex-col">
            <div className="flex-1 min-h-0">
              <AgentTimeline
                state={gitState}
                headerExtra={
                  <button
                    type="button"
                    onClick={() => setShowDelta((s) => !s)}
                    aria-pressed={showDelta}
                    className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-semibold transition-colors ${
                      showDelta
                        ? "border-pink-400/50 bg-pink-500/15 text-pink-200"
                        : "border-white/15 bg-white/5 text-white/60 hover:bg-white/10"
                    }`}
                  >
                    <GitFork className="h-3 w-3" /> {showDelta ? "Hide" : "Show"} delta graph
                  </button>
                }
              />
            </div>
          </div>
        ) : sourceTab === "upload" && docJobId ? (
          <div className="flex flex-1 min-h-0 flex-col">
            <div className="flex-1 min-h-0">
              <AgentTimeline state={docState} />
            </div>
          </div>
        ) : (
        <>
        <div className="p-5 border-b border-[var(--card-border)] bg-[var(--background)]/80 backdrop-blur-md sticky top-0 z-30">
          <h3 className="text-sm font-semibold tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-500 flex items-center gap-2">
            <Network className="w-4 h-4 text-blue-400" /> Pipeline Orchestration
          </h3>
        </div>

        <div className="flex-1 p-6 flex flex-col items-center justify-start space-y-8 overflow-y-auto">

          {Object.keys(stepResults).length === 0 && activeAgent === "idle" && !fileName && !gitJobId && (
            <EmptyState
              icon={<Upload />}
              title="Drop a document or paste a Git repo URL"
              body="We'll parse, embed, extract entities, and build the knowledge graph live."
            />
          )}

          {/* Main Coordinator/Processing Agent */}
          <div className="relative mt-4">
             <div className="absolute inset-0 bg-orange-500 blur-2xl opacity-20 rounded-full" />
             <div className={`flex flex-col items-center gap-3 transition-all duration-500 z-20 ${
                activeAgent === "ProcessingAgent"
                  ? "scale-110 drop-shadow-[0_0_20px_rgba(249,115,22,0.4)]"
                  : "opacity-80 scale-95"
              }`}>
                <div className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300 ${
                  activeAgent === "ProcessingAgent" ? "bg-gradient-to-br from-orange-500 to-amber-600 shadow-[inset_0_2px_10px_rgba(255,255,255,0.2)] border-2 border-orange-300/50" : "bg-[var(--card)] border border-[var(--card-border)]"
                }`}>
                  <Combine className={`w-7 h-7 ${activeAgent === "ProcessingAgent" ? "text-white" : "text-orange-500"}`} />
                </div>
                <div className="text-center">
                  <span className={`block font-bold text-sm ${activeAgent === "ProcessingAgent" ? "text-white" : "text-[var(--foreground)]"}`}>ProcessingAgent</span>
                  <span className="text-[10px] tracking-widest opacity-60 uppercase">Controller</span>
                </div>
              </div>
          </div>

          <div className="w-px h-8 bg-gradient-to-b from-orange-500/40 to-blue-500/40" />

          {/* Sotto-fasi Sequenziali */}
          <div className="flex flex-col gap-4 w-full">

             {/* 1. Metadata Extraction */}
             <details className={`group transition-all duration-500 rounded-2xl border ${activeAgent === "Metadata" ? "bg-cyan-500/5 border-cyan-400 shadow-[0_0_20px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/50" : stepResults["Metadata"] ? "bg-white/5 border-white/10" : "bg-transparent border-transparent opacity-60"}`} open={activeAgent === "Metadata" || !!stepResults["Metadata"]}>
               <summary className="flex items-center gap-4 cursor-pointer p-2 list-none outline-none">
                 <div className={`w-10 h-10 shrink-0 rounded-xl flex items-center justify-center transition-all duration-300 ${activeAgent === "Metadata" ? "bg-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.4)]" : "bg-[var(--card)] border border-[var(--card-border)]"}`}>
                   <FileText className={`w-4 h-4 ${activeAgent === "Metadata" ? "text-cyan-400" : "text-[var(--foreground)]"}`} />
                 </div>
                 <div className="flex flex-col flex-1">
                   <span className={`font-bold text-sm flex items-center justify-between ${activeAgent === "Metadata" ? "text-cyan-400" : "text-[var(--foreground)]"}`}>1. Metadata {stepResults["Metadata"] && <span className="text-xs text-cyan-500">Done</span>}</span>
                   <span className="text-[10px] opacity-60">Title, Author, Type, Date</span>
                 </div>
                 <ChevronDown className="w-4 h-4 text-white/50 group-open:rotate-180 transition-transform mr-2" />
               </summary>
               <div className="px-4 pb-4">
                 {activeAgent === "Metadata" && !stepResults["Metadata"] && <div className="text-xs text-cyan-400/80 animate-pulse mt-2 flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin"/> Extracting metadata...</div>}
                 {stepResults["Metadata"] && formatRightSideResult(stepResults["Metadata"])}
               </div>
             </details>

             {/* 2. Parallel Processing (Embeddings + Graph + Entity Search) */}
             <details className={`group transition-all duration-500 rounded-2xl border ${activeAgent === "Processing" ? "bg-purple-500/5 border-purple-400 shadow-[0_0_20px_rgba(168,85,247,0.15)] ring-1 ring-purple-500/50" : stepResults["Processing"] ? "bg-white/5 border-white/10" : "bg-transparent border-transparent opacity-60"}`} open={activeAgent === "Processing" || !!stepResults["Processing"]}>
               <summary className="flex items-center gap-4 cursor-pointer p-2 list-none outline-none">
                 <div className={`w-10 h-10 shrink-0 rounded-xl flex items-center justify-center transition-all duration-300 ${activeAgent === "Processing" ? "bg-purple-500/20 shadow-[0_0_15px_rgba(168,85,247,0.4)]" : "bg-[var(--card)] border border-[var(--card-border)]"}`}>
                   <GitFork className={`w-4 h-4 ${activeAgent === "Processing" ? "text-purple-400" : "text-[var(--foreground)]"}`} />
                 </div>
                 <div className="flex flex-col flex-1">
                   <span className={`font-bold text-sm flex items-center justify-between ${activeAgent === "Processing" ? "text-purple-400" : "text-[var(--foreground)]"}`}>2. Parallel Processing {stepResults["Processing"] && <span className="text-xs text-purple-500">Done</span>}</span>
                   <span className="text-[10px] opacity-60">Embeddings + Graph + Entity Search (concurrent)</span>
                 </div>
                 <ChevronDown className="w-4 h-4 text-white/50 group-open:rotate-180 transition-transform mr-2" />
               </summary>
               <div className="px-4 pb-4">
                 {activeAgent === "Processing" && !stepResults["Processing"] && (
                   <div className="mt-2 space-y-2">
                     <div className="text-xs text-purple-400/80 animate-pulse flex items-center gap-2"><Fingerprint className="w-3 h-3"/> Chunking + Embeddings...</div>
                     <div className="text-xs text-pink-400/80 animate-pulse flex items-center gap-2"><Network className="w-3 h-3"/> ArchiMate Graph Extraction...</div>
                     <div className="text-xs text-yellow-400/80 animate-pulse flex items-center gap-2"><Search className="w-3 h-3"/> Entity Reconciliation...</div>
                   </div>
                 )}
                 {stepResults["Processing"] && formatRightSideResult(stepResults["Processing"])}
               </div>
             </details>

             {/* 3. Spanner Write */}
             <details className={`group transition-all duration-500 rounded-2xl border ${activeAgent === "Spanner" ? "bg-green-500/5 border-green-400 shadow-[0_0_20px_rgba(34,197,94,0.15)] ring-1 ring-green-500/50" : stepResults["Spanner"] ? "bg-white/5 border-white/10" : "bg-transparent border-transparent opacity-60"}`} open={activeAgent === "Spanner" || !!stepResults["Spanner"]}>
               <summary className="flex items-center gap-4 cursor-pointer p-2 list-none outline-none">
                 <div className={`w-10 h-10 shrink-0 rounded-xl flex items-center justify-center transition-all duration-300 ${activeAgent === "Spanner" ? "bg-green-500/20 shadow-[0_0_15px_rgba(34,197,94,0.4)]" : "bg-[var(--card)] border border-[var(--card-border)]"}`}>
                   <Database className={`w-4 h-4 ${activeAgent === "Spanner" ? "text-green-400" : "text-[var(--foreground)]"}`} />
                 </div>
                 <div className="flex flex-col flex-1">
                   <span className={`font-bold text-sm flex items-center justify-between ${activeAgent === "Spanner" ? "text-green-400" : "text-[var(--foreground)]"}`}>3. Spanner Write {stepResults["Spanner"] && <span className="text-xs text-green-500">Done</span>}</span>
                   <span className="text-[10px] opacity-60">Persist graph + chunks to Cloud Spanner</span>
                 </div>
                 <ChevronDown className="w-4 h-4 text-white/50 group-open:rotate-180 transition-transform mr-2" />
               </summary>
               <div className="px-4 pb-4">
                 {activeAgent === "Spanner" && !stepResults["Spanner"] && <div className="text-xs text-green-400/80 animate-pulse mt-2 flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin"/> Committing transaction...</div>}
                 {stepResults["Spanner"] && formatRightSideResult(stepResults["Spanner"])}
               </div>
             </details>

          </div>

          {/* Status Indicator */}
          {activeAgent !== "idle" && !pipelineComplete && (
            <div className="mt-auto flex items-center gap-2 bg-white/5 border border-white/10 px-4 py-2 text-center rounded-full shadow-lg">
               <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse flex-shrink-0" />
               <span className="text-[11px] font-semibold tracking-wide">
                 {activeAgent === "ProcessingAgent" ? "Initializing pipeline..." :
                  activeAgent === "Metadata" ? "Extracting metadata [1/3]..." :
                  activeAgent === "Processing" ? "Parallel processing: embeddings + graph + search [2/3]..." :
                  activeAgent === "Spanner" ? "Writing to Cloud Spanner [3/3]..." :
                  activeAgent === "Complete" ? "Finalizing..." :
                  "Processing..."}
               </span>
            </div>
          )}

          {pipelineComplete && (
            <div className="mt-auto flex items-center gap-2 bg-green-500/10 border border-green-500/30 px-4 py-2 text-center rounded-full shadow-lg">
               <div className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
               <span className="text-[11px] font-semibold tracking-wide text-green-400">
                 Pipeline completed successfully
               </span>
            </div>
          )}

        </div>
        </>
        )}
      </div>
    </main>
  );
}
