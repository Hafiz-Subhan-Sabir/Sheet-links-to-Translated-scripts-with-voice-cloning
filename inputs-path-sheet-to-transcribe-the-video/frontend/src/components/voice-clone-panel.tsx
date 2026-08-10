"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ProgressBar } from "@/components/progress-bar";
import { toast } from "@/hooks/use-toast";
import { api, waitForJob } from "@/lib/api";
import { normalizeProgress } from "@/lib/progress";
import type {
  JobStatusResponse,
  OutputQueueResponse,
  OutputRow,
  VoiceInfo,
  VoiceJobResult,
} from "@/lib/types";
import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  Mic,
  RefreshCw,
  Square,
  Upload,
  Volume2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const LANGUAGE_OPTIONS = [
  "English Transcript",
  "British English",
  "American English",
  "Spanish",
  "Chinese (Simplified)",
  "Hindi",
  "Arabic",
  "Portuguese",
  "French",
  "Russian",
  "Japanese",
  "German",
  "Korean",
];

const selectClass = cn(
  "flex h-11 w-full rounded-xl border border-border bg-[var(--card)] px-3 text-sm text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
);

interface VoiceClonePanelProps {
  connected: boolean;
  outputConfigured: boolean;
}

export function VoiceClonePanel({ connected, outputConfigured }: VoiceClonePanelProps) {
  const [output, setOutput] = useState<OutputQueueResponse | null>(null);
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [elevenlabs, setElevenlabs] = useState(false);
  const [selectedVoice, setSelectedVoice] = useState<string>("");
  const [newVoiceName, setNewVoiceName] = useState("");
  const [sampleFile, setSampleFile] = useState<File | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [languageColumn, setLanguageColumn] = useState("English Transcript");
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);
  const [statusStep, setStatusStep] = useState("");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<VoiceJobResult | null>(null);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const refresh = useCallback(async () => {
    if (!connected || !outputConfigured) return;
    setLoading(true);
    try {
      const [out, voiceList] = await Promise.all([api.batchOutput(), api.voiceList()]);
      setOutput(out);
      setVoices(voiceList.voices);
      setElevenlabs(voiceList.elevenlabs_configured);
      setOutputDir((prev) => prev || voiceList.voice_output_dir || "");
      setSelectedVoice((prev) => prev || (voiceList.voices[0]?.id ?? ""));
    } catch (err) {
      toast({
        title: "Could not load",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [connected, outputConfigured]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggleRow = (index: number) => {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const selectReady = () => {
    if (!output) return;
    setSelectedRows(
      new Set(output.rows.filter((r) => r.status === "ready_for_voice").map((r) => r.row_index))
    );
  };

  const handleCloneNew = async () => {
    if (!newVoiceName.trim()) {
      toast({ title: "Enter a voice name", variant: "destructive" });
      return;
    }
    if (!sampleFile) {
      toast({ title: "Upload or record a sample first", variant: "destructive" });
      return;
    }
    setCloning(true);
    try {
      const res = await api.voiceClone(newVoiceName.trim(), sampleFile);
      toast({ title: "Voice saved", description: `“${res.voice.name}” is ready in the dropdown.` });
      setSelectedVoice(res.voice.id);
      setNewVoiceName("");
      setSampleFile(null);
      await refresh();
    } catch (err) {
      toast({
        title: "Clone failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setCloning(false);
    }
  };

  const handleSynthesize = async () => {
    if (!selectedVoice) {
      toast({ title: "Pick a saved voice (or create one)", variant: "destructive" });
      return;
    }
    if (selectedRows.size === 0) {
      toast({ title: "Select at least one transcript", variant: "destructive" });
      return;
    }
    setSynthesizing(true);
    setResult(null);
    setProgress(0);
    setStatusStep("Starting…");
    try {
      if (outputDir.trim()) await api.voiceSetOutputDir(outputDir.trim());
      const start = await api.voiceSynthesize({
        voice_id: selectedVoice,
        output_row_indexes: Array.from(selectedRows),
        language_column: languageColumn,
        output_dir: outputDir.trim() || undefined,
      });
      const finalStatus = await waitForJob(
        start.job_id,
        (status: JobStatusResponse) => {
          setStatusStep(status.step || "Synthesizing…");
          setProgress(normalizeProgress(status.progress));
        },
        2000,
        3 * 60 * 60 * 1000
      );
      const jobResult = finalStatus.result as VoiceJobResult | null;
      setResult(jobResult);
      toast({
        title: "Audio ready",
        description: `${jobResult?.processed ?? 0} file(s) saved${
          jobResult?.output_dir ? ` → ${jobResult.output_dir}` : ""
        }`,
      });
      await refresh();
    } catch (err) {
      toast({
        title: "Failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setSynthesizing(false);
    }
  };

  const handleMarkDone = async () => {
    if (selectedRows.size === 0) {
      toast({ title: "Select rows to mark done", variant: "destructive" });
      return;
    }
    try {
      const res = await api.markDone(Array.from(selectedRows));
      toast({ title: "Marked done", description: `${res.updated} row(s) skipped voice cloning.` });
      setSelectedRows(new Set());
      await refresh();
    } catch (err) {
      toast({
        title: "Failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const file = new File([blob], `recording-${Date.now()}.webm`, { type: "audio/webm" });
        setSampleFile(file);
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      toast({
        title: "Microphone blocked",
        description: err instanceof Error ? err.message : "Allow mic access",
        variant: "destructive",
      });
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  if (!connected || !outputConfigured) {
    return (
      <div className="surface flex h-full flex-col items-start justify-center gap-3 p-8">
        <Volume2 className="h-8 w-8 text-[var(--accent)]" />
        <h2 className="text-xl font-bold">Voice cloning</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Finish Setup and run Transcribe first. Then come here to clone a voice onto your scripts — or mark them
          done.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div>
        <h2 className="text-xl font-extrabold tracking-tight sm:text-2xl">Voice</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Sample → pick voice → select rows → clone. Or skip with Mark done.
        </p>
        {!elevenlabs && (
          <p className="mt-2 rounded-xl bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] px-3 py-2 text-sm text-[var(--warn)]">
            Add <code className="text-xs">FISH_API_KEY</code> in backend <code className="text-xs">.env</code> to
            enable Fish Audio cloning.
          </p>
        )}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="surface scroll-pane max-h-[70vh] space-y-4 p-4 sm:p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Saved voice</Label>
              <select
                className={selectClass}
                value={selectedVoice}
                onChange={(e) => setSelectedVoice(e.target.value)}
              >
                <option value="">Choose a voice…</option>
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Language to speak</Label>
              <select
                className={selectClass}
                value={languageColumn}
                onChange={(e) => setLanguageColumn(e.target.value)}
              >
                {LANGUAGE_OPTIONS.map((col) => (
                  <option key={col} value={col}>
                    {col}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="surface-soft space-y-3 p-3">
            <p className="text-sm font-semibold">New voice from sample</p>
            <div className="space-y-2">
              <Label>Name</Label>
              <Input
                value={newVoiceName}
                onChange={(e) => setNewVoiceName(e.target.value)}
                placeholder="e.g. Host Voice"
              />
            </div>
            <div className="space-y-2">
              <Label>Sample file</Label>
              <Input
                type="file"
                accept="audio/*,.mp3,.wav,.m4a,.webm"
                onChange={(e) => setSampleFile(e.target.files?.[0] ?? null)}
              />
              {sampleFile && <p className="truncate text-xs text-muted-foreground">{sampleFile.name}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              {!recording ? (
                <Button type="button" variant="outline" size="sm" onClick={startRecording}>
                  <Mic className="h-4 w-4" />
                  Record
                </Button>
              ) : (
                <Button type="button" variant="destructive" size="sm" onClick={stopRecording}>
                  <Square className="h-4 w-4" />
                  Stop
                </Button>
              )}
              <Button size="sm" onClick={handleCloneNew} disabled={cloning || !elevenlabs}>
                {cloning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                Save voice
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Save audio files to</Label>
            <Input
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
              placeholder="C:\Voices\output"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleSynthesize} disabled={synthesizing || !elevenlabs} size="lg">
              {synthesizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
              Clone selected
            </Button>
            <Button variant="secondary" onClick={handleMarkDone}>
              <CheckCircle2 className="h-4 w-4" />
              Mark done
            </Button>
            <Button variant="outline" onClick={selectReady}>
              Select ready
            </Button>
            <Button variant="outline" onClick={refresh} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </Button>
            {output?.output_sheet_url && (
              <Button variant="outline" asChild>
                <a href={output.output_sheet_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-4 w-4" />
                  Sheet
                </a>
              </Button>
            )}
          </div>

          {synthesizing && <ProgressBar value={progress} stepLabel={statusStep} />}
          {result && !synthesizing && (
            <p className="text-xs text-muted-foreground">
              Last run: {result.processed} ok · {result.failed} failed · {result.output_dir}
            </p>
          )}
        </div>

        <div className="surface flex min-h-0 flex-col overflow-hidden">
          <div className="border-b border-border px-4 py-3">
            <h3 className="font-semibold">Transcripts</h3>
            <p className="text-xs text-muted-foreground">
              {output?.ready_for_voice_count ?? 0} ready · {output?.voice_cloned_count ?? 0} voiced ·{" "}
              {output?.marked_done_count ?? 0} done
            </p>
          </div>
          <div className="scroll-pane max-h-[60vh] flex-1 space-y-2 p-3">
            {!output || output.rows.length === 0 ? (
              <p className="px-2 py-10 text-center text-sm text-muted-foreground">
                No output rows yet. Run Transcribe first.
              </p>
            ) : (
              output.rows.map((row: OutputRow) => (
                <label
                  key={row.row_index}
                  className="row-item flex cursor-pointer items-start gap-3"
                  data-status={
                    row.status === "ready_for_voice"
                      ? "pending"
                      : row.status === "voice_cloned"
                        ? "done"
                        : undefined
                  }
                >
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 accent-[var(--accent)]"
                    checked={selectedRows.has(row.row_index)}
                    onChange={() => toggleRow(row.row_index)}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-semibold">{row.video_name}</span>
                      <Badge variant="secondary">{row.status || "—"}</Badge>
                      {row.category && <Badge variant="outline">{row.category}</Badge>}
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {row.voice_notes || row.date_transcribed || row.video_length || "—"}
                    </p>
                    {row.docs_link && (
                      <a
                        href={row.docs_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-[var(--accent)] hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <ExternalLink className="h-3 w-3" />
                        Open Doc
                      </a>
                    )}
                  </div>
                </label>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
