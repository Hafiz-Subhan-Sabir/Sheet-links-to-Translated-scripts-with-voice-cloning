"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProgressBar } from "@/components/progress-bar";
import { toast } from "@/hooks/use-toast";
import { api, waitForJob } from "@/lib/api";
import { computeQueueStats, normalizeQueueStatus } from "@/lib/queue-stats";
import type { BatchConfigResponse, BatchJobResult, BatchQueueResponse, BatchRow, JobStatusResponse } from "@/lib/types";
import { normalizeProgress } from "@/lib/progress";
import {
  AlertTriangle,
  ArrowRight,
  ExternalLink,
  FileSpreadsheet,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
} from "lucide-react";

interface BatchWorkspaceProps {
  connected: boolean;
  sheetConfigured: boolean;
  outputConfigured?: boolean;
  inputSheetUrl?: string | null;
  onStepChange: (step: "setup" | "queue" | "processing" | "done") => void;
  onOpenVoice?: () => void;
}

type BadgeVariant = "default" | "secondary" | "warning" | "local" | "success" | "pending" | "activity";

function statusVariant(status: string): BadgeVariant {
  switch (normalizeQueueStatus(status)) {
    case "done":
      return "success";
    case "processing":
      return "secondary";
    case "failed":
      return "warning";
    case "pending":
      return "pending";
    default:
      return "local";
  }
}

function isActivityMessage(status: string, message?: string | null): boolean {
  if (normalizeQueueStatus(status) !== "processing" || !message) return false;
  return (
    message.includes("Transcribing") ||
    message.includes("Translating") ||
    message.includes("English") ||
    message.includes("Classifying") ||
    message.includes("Creating") ||
    message.includes("Writing") ||
    message.includes("Saving") ||
    message.endsWith("…")
  );
}

export function BatchWorkspace({
  connected,
  sheetConfigured,
  outputConfigured = false,
  inputSheetUrl,
  onStepChange,
  onOpenVoice,
}: BatchWorkspaceProps) {
  const [queue, setQueue] = useState<BatchQueueResponse | null>(null);
  const [config, setConfig] = useState<BatchConfigResponse | null>(null);
  const [loadingQueue, setLoadingQueue] = useState(false);
  const [running, setRunning] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [statusStep, setStatusStep] = useState("");
  const [progress, setProgress] = useState(0);
  const [batchResult, setBatchResult] = useState<BatchJobResult | null>(null);
  const userStoppedRef = useRef(false);
  const activeJobRef = useRef<string | null>(null);

  const loadQueueSilent = useCallback(async () => {
    if (!connected || !sheetConfigured) return null;
    try {
      const data = await api.batchQueue();
      setQueue(data);
      if (!running) {
        onStepChange(data.pending_count > 0 ? "queue" : data.total_count > 0 ? "done" : "queue");
      }
      return data;
    } catch {
      return null;
    }
  }, [connected, sheetConfigured, onStepChange, running]);

  const refreshQueue = useCallback(async () => {
    if (!connected || !sheetConfigured) return;
    setLoadingQueue(true);
    try {
      const [data, cfg] = await Promise.all([api.batchQueue(), api.batchConfig()]);
      setQueue(data);
      setConfig(cfg);
      if (!running) {
        onStepChange(data.pending_count > 0 ? "queue" : data.total_count > 0 ? "done" : "queue");
      }
    } catch (err) {
      toast({
        title: "Could not load queue",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoadingQueue(false);
    }
  }, [connected, sheetConfigured, onStepChange, running]);

  useEffect(() => {
    refreshQueue();
  }, [refreshQueue]);

  useEffect(() => {
    if (!connected || !sheetConfigured) return;
    const id = window.setInterval(() => {
      void loadQueueSilent();
    }, 3000);
    return () => window.clearInterval(id);
  }, [connected, sheetConfigured, loadQueueSilent]);

  const stats = queue ? computeQueueStats(queue) : null;

  const handleRunBatch = async () => {
    if (!connected || !sheetConfigured) return;
    userStoppedRef.current = false;
    setRunning(true);
    setBatchResult(null);
    setProgress(0);
    setStatusStep("Starting…");
    onStepChange("processing");

    try {
      const start = await api.batchRun();
      activeJobRef.current = start.job_id;
      const workers = start.batch_workers ?? config?.batch_workers ?? 3;
      toast({
        title: "Processing started",
        description: `${start.pending_count} video(s) · ${workers} workers`,
      });

      const finalStatus = await waitForJob(
        start.job_id,
        (status: JobStatusResponse) => {
          setStatusStep(status.step || "Processing…");
          setProgress(normalizeProgress(status.progress));
        },
        1500,
        6 * 60 * 60 * 1000
      );

      if (userStoppedRef.current) {
        onStepChange("queue");
        return;
      }

      setBatchResult((finalStatus.result as BatchJobResult | null | undefined) ?? null);
      onStepChange("done");
      await refreshQueue();

      const processed = finalStatus.result ? (finalStatus.result as BatchJobResult).processed : 0;
      const failed = finalStatus.result ? (finalStatus.result as BatchJobResult).failed : 0;
      toast({
        title: "Batch complete",
        description: `${processed} succeeded, ${failed} failed. You can clone voices next.`,
        variant: failed > 0 ? "destructive" : "default",
      });
    } catch (err) {
      if (userStoppedRef.current) {
        toast({ title: "Stopped", description: "Batch was reset." });
        onStepChange("queue");
        await refreshQueue();
        return;
      }
      toast({
        title: "Batch failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
      onStepChange("queue");
      await refreshQueue();
    } finally {
      activeJobRef.current = null;
      setRunning(false);
    }
  };

  const handleResetBatch = async () => {
    setResetting(true);
    userStoppedRef.current = true;
    try {
      const result = await api.batchReset();
      setRunning(false);
      setBatchResult(null);
      setProgress(0);
      setStatusStep("");
      await refreshQueue();
      toast({
        title: "Reset",
        description: result.sheet_rows_reset
          ? `${result.sheet_rows_reset} row(s) set back to pending.`
          : result.cleared_lock
            ? "Cleared stuck job. Try again."
            : "Nothing was running.",
      });
      onStepChange("queue");
    } catch (err) {
      toast({
        title: "Reset failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setResetting(false);
    }
  };

  const outputSheetUrl = queue?.output_sheet_url ?? batchResult?.output_sheet_url;
  const canRun =
    connected &&
    sheetConfigured &&
    outputConfigured &&
    (queue?.pending_count ?? 0) > 0 &&
    !running &&
    !resetting;
  const workers = config?.batch_workers ?? 3;

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight sm:text-2xl">Run batch</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            One click processes pending videos → translations → Docs → output sheet.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {inputSheetUrl && (
            <Button variant="outline" size="sm" asChild>
              <a href={inputSheetUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-3.5 w-3.5" />
                Input
              </a>
            </Button>
          )}
          {outputSheetUrl && (
            <Button variant="outline" size="sm" asChild>
              <a href={outputSheetUrl} target="_blank" rel="noopener noreferrer">
                <FileSpreadsheet className="h-3.5 w-3.5" />
                Output
              </a>
            </Button>
          )}
        </div>
      </div>

      {(!connected || !sheetConfigured || !outputConfigured) && (
        <div className="surface-soft px-4 py-3 text-sm text-[var(--warn)]">
          Finish Setup first — connect Google and save both sheet links.
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <div className="stat-chip" data-tone="pending">
            <span className="label">Pending</span>
            <span className="value">{stats.pending}</span>
          </div>
          <div className="stat-chip" data-tone="processing">
            <span className="label">Working</span>
            <span className="value">{stats.processing}</span>
          </div>
          <div className="stat-chip" data-tone="done">
            <span className="label">Done</span>
            <span className="value">{stats.done}</span>
          </div>
          <div className="stat-chip" data-tone="failed">
            <span className="label">Failed</span>
            <span className="value">{stats.failed}</span>
          </div>
          <div className="stat-chip col-span-2 sm:col-span-1">
            <span className="label">Total</span>
            <span className="value">{stats.total}</span>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="lg" onClick={handleRunBatch} disabled={!canRun}>
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? "Processing…" : "Process pending"}
        </Button>
        <Button
          variant="outline"
          onClick={refreshQueue}
          disabled={!connected || !sheetConfigured || loadingQueue || running}
        >
          {loadingQueue ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
        <Button
          variant="outline"
          onClick={handleResetBatch}
          disabled={!connected || !sheetConfigured || resetting}
        >
          {resetting ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
          Stop / reset
        </Button>
        {batchResult && !running && onOpenVoice && (
          <Button variant="secondary" onClick={onOpenVoice}>
            Go to Voice
            <ArrowRight className="h-4 w-4" />
          </Button>
        )}
        <span className="text-xs text-muted-foreground">{workers} parallel workers · live sync</span>
      </div>

      {running && (
        <div className="surface p-4">
          <ProgressBar value={progress} stepLabel={statusStep} />
        </div>
      )}

      {batchResult && !running && (
        <div className="surface-soft flex items-start gap-3 px-4 py-3 text-sm">
          <div>
            <p className="font-semibold text-[var(--success)]">Last run finished</p>
            <p className="text-muted-foreground">
              {batchResult.processed} processed · {batchResult.failed} failed — open Voice to clone, or mark done.
            </p>
          </div>
        </div>
      )}

      <div className="surface min-h-0 flex-1 overflow-hidden">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">Queue</h3>
        </div>
        <div className="scroll-pane max-h-[42vh] space-y-2 p-3 sm:max-h-[48vh]">
          {!queue || queue.rows.length === 0 ? (
            <p className="px-2 py-8 text-center text-sm text-muted-foreground">
              No rows yet. Add videos to the input sheet with status <code className="text-xs">pending</code>.
            </p>
          ) : (
            queue.rows.map((row: BatchRow) => {
              const rowStatus = normalizeQueueStatus(row.status);
              const activity = isActivityMessage(row.status, row.error);
              return (
                <div key={row.row_index} className="row-item" data-status={rowStatus}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">#{row.row_index}</span>
                    <Badge variant={statusVariant(row.status)}>{rowStatus}</Badge>
                  </div>
                  <p className="mt-1.5 truncate font-semibold">{row.program_title || "—"}</p>
                  <p className="truncate font-mono text-xs text-muted-foreground">{row.video_path || "—"}</p>
                  {row.error ? (
                    activity ? (
                      <Badge variant="activity" className="mt-2 max-w-full truncate">
                        {row.error}
                      </Badge>
                    ) : (
                      <p className="mt-2 flex items-start gap-1 text-xs text-[var(--danger)]">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span className="line-clamp-2">{row.error}</span>
                      </p>
                    )
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
