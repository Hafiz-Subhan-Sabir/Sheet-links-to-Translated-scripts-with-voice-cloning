"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ProgressBar } from "@/components/progress-bar";
import { toast } from "@/hooks/use-toast";
import { api, waitForJob } from "@/lib/api";
import { normalizeProgress } from "@/lib/progress";
import type { JobStatusResponse, VoiceInfo } from "@/lib/types";
import { Download, Loader2, Mic, Square, Upload, Volume2 } from "lucide-react";
import { cn } from "@/lib/utils";

const selectClass = cn(
  "flex h-11 w-full rounded-xl border border-border bg-[var(--card)] px-3 text-sm text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SpeakWorkspaceProps {
  onBack: () => void;
}

function downloadUrlFor(filename: string, inline = false) {
  const base = `${API_URL}/api/voice/download/${encodeURIComponent(filename)}`;
  return inline ? `${base}?inline=1` : base;
}

async function saveMp3ToDisk(filename: string) {
  const res = await fetch(downloadUrlFor(filename, false));
  if (!res.ok) {
    throw new Error(res.status === 404 ? "File not found" : `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

export function SpeakWorkspace({ onBack }: SpeakWorkspaceProps) {
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [fishOk, setFishOk] = useState(false);
  const [selectedVoice, setSelectedVoice] = useState("");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("my-script");
  const [newVoiceName, setNewVoiceName] = useState("");
  const [sampleFile, setSampleFile] = useState<File | null>(null);
  const [sampleUrl, setSampleUrl] = useState("");
  const [sampleStartSec, setSampleStartSec] = useState("0");
  const [sampleDurationSec, setSampleDurationSec] = useState("30");
  const [recording, setRecording] = useState(false);
  const [savingVoice, setSavingVoice] = useState(false);
  const [cloningFromUrl, setCloningFromUrl] = useState(false);
  const [urlCloneProgress, setUrlCloneProgress] = useState(0);
  const [urlCloneStep, setUrlCloneStep] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusStep, setStatusStep] = useState("");
  const [resultFilename, setResultFilename] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const refreshVoices = useCallback(async () => {
    try {
      const list = await api.voiceList();
      setVoices(list.voices);
      setFishOk(list.elevenlabs_configured);
      setSelectedVoice((prev) => prev || list.voices[0]?.id || "");
    } catch (err) {
      toast({
        title: "Could not load voices",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    }
  }, []);

  useEffect(() => {
    void refreshVoices();
  }, [refreshVoices]);

  const selectedVoiceName = voices.find((v) => v.id === selectedVoice)?.name || "";

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const file = new File([blob], `recording-${Date.now()}.webm`, { type: "audio/webm" });
        setSampleFile(file);
        toast({ title: "Recording ready", description: "Click Save voice to train it." });
      };
      recorder.start();
      setRecording(true);
    } catch {
      toast({ title: "Mic blocked", description: "Allow microphone access.", variant: "destructive" });
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const saveVoice = async () => {
    if (!newVoiceName.trim()) {
      toast({ title: "Name the voice", variant: "destructive" });
      return;
    }
    if (!sampleFile) {
      toast({ title: "Upload or record a sample", variant: "destructive" });
      return;
    }
    setSavingVoice(true);
    try {
      const res = await api.voiceClone(newVoiceName.trim(), sampleFile);
      toast({ title: "Voice saved", description: `"${res.voice.name}" is ready to use.` });
      setSelectedVoice(res.voice.id);
      setNewVoiceName("");
      setSampleFile(null);
      await refreshVoices();
      setSelectedVoice(res.voice.id);
    } catch (err) {
      toast({
        title: "Save failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setSavingVoice(false);
    }
  };

  const cloneFromUrl = async () => {
    const url = sampleUrl.trim();
    if (!url) {
      toast({ title: "Paste a video/audio URL", variant: "destructive" });
      return;
    }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      toast({ title: "URL must start with http:// or https://", variant: "destructive" });
      return;
    }
    const start = Number(sampleStartSec);
    const duration = Number(sampleDurationSec);
    setCloningFromUrl(true);
    setUrlCloneProgress(0);
    setUrlCloneStep("Starting…");
    try {
      const startJob = await api.voiceCloneFromUrl({
        url,
        name: newVoiceName.trim() || undefined,
        start_sec: Number.isFinite(start) ? start : 0,
        duration_sec: Number.isFinite(duration) ? duration : 30,
      });
      const finalStatus = await waitForJob(
        startJob.job_id,
        (status: JobStatusResponse) => {
          setUrlCloneStep(status.step || "Cloning…");
          setUrlCloneProgress(normalizeProgress(status.progress));
        },
        2000,
        30 * 60 * 1000
      );
      const result = (finalStatus.result || {}) as {
        voice?: VoiceInfo;
        sample_filename?: string;
        source_title?: string;
      };
      if (!result.voice?.id) {
        throw new Error("Clone finished but no voice was returned");
      }
      toast({
        title: "Voice cloned from URL",
        description: `"${result.voice.name}" ready — paste any script and Make MP3.`,
      });
      setSampleUrl("");
      setNewVoiceName("");
      await refreshVoices();
      setSelectedVoice(result.voice.id);
    } catch (err) {
      toast({
        title: "Clone from URL failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setCloningFromUrl(false);
    }
  };

  const makeMp3 = async () => {
    if (!selectedVoice) {
      toast({ title: "Pick a voice", variant: "destructive" });
      return;
    }
    if (!text.trim()) {
      toast({ title: "Paste text to speak", variant: "destructive" });
      return;
    }
    setSpeaking(true);
    setProgress(0);
    setStatusStep("Starting…");
    setResultFilename(null);
    setPreviewUrl(null);
    try {
      const start = await api.voiceSpeakText({
        voice_id: selectedVoice,
        text: text.trim(),
        title: title.trim() || "spoken",
      });
      const finalStatus = await waitForJob(
        start.job_id,
        (status: JobStatusResponse) => {
          setStatusStep(status.step || "Speaking…");
          setProgress(normalizeProgress(status.progress));
        },
        1500,
        3 * 60 * 60 * 1000
      );
      const result = (finalStatus.result || {}) as {
        filename?: string;
        voice_name?: string;
        files?: string[];
      };
      const filename = result.filename || result.files?.[0]?.split(/[/\\]/).pop();
      if (!filename) {
        throw new Error("MP3 was created but filename was missing");
      }
      setResultFilename(filename);
      // Preview only — inline so the browser does NOT auto-download
      setPreviewUrl(downloadUrlFor(filename, true));
      toast({
        title: "MP3 ready",
        description: `${filename} — preview below, then hit Download when you want the file.`,
      });
    } catch (err) {
      toast({
        title: "Speak failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setSpeaking(false);
    }
  };

  const handleDownload = async () => {
    if (!resultFilename) return;
    setDownloading(true);
    try {
      await saveMp3ToDisk(resultFilename);
      toast({ title: "Downloaded", description: resultFilename });
    } catch (err) {
      toast({
        title: "Download failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight sm:text-2xl">Text → MP3</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Paste any script. Pick a saved voice, or record/upload a new sample, then make an MP3.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={onBack}>
          All workflows
        </Button>
      </div>

      {!fishOk && (
        <p className="rounded-xl bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] px-3 py-2 text-sm text-[var(--warn)]">
          Add <code className="text-xs">FISH_API_KEY</code> in backend <code className="text-xs">.env</code>.
        </p>
      )}

      <div className="surface-soft space-y-3 p-4">
        <p className="text-sm font-semibold">1. Voice</p>
        <div className="space-y-2">
          <Label>Use saved voice</Label>
          <select
            className={selectClass}
            value={selectedVoice}
            onChange={(e) => setSelectedVoice(e.target.value)}
          >
            <option value="">Choose a voice…</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
                {v.sample_filename ? ` · ${v.sample_filename}` : ""}
              </option>
            ))}
          </select>
        </div>

        <div className="rounded-xl border border-border p-3 space-y-3">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
            Or clone a voice from a URL (YouTube etc.)
          </p>
          <p className="text-xs text-muted-foreground">
            We download the audio, trim a short sample, clone it with Fish, then you can speak any script.
            Prefer a clean speaking section (no loud music).
          </p>
          <div className="space-y-2">
            <Label>Sample URL</Label>
            <Input
              value={sampleUrl}
              onChange={(e) => setSampleUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-2 sm:col-span-1">
              <Label>Voice name (optional)</Label>
              <Input
                value={newVoiceName}
                onChange={(e) => setNewVoiceName(e.target.value)}
                placeholder="e.g. Channel host"
              />
            </div>
            <div className="space-y-2">
              <Label>Start (sec)</Label>
              <Input
                type="number"
                min={0}
                step={1}
                value={sampleStartSec}
                onChange={(e) => setSampleStartSec(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Length (sec)</Label>
              <Input
                type="number"
                min={5}
                max={90}
                step={1}
                value={sampleDurationSec}
                onChange={(e) => setSampleDurationSec(e.target.value)}
              />
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={cloneFromUrl}
            disabled={cloningFromUrl || !fishOk}
          >
            {cloningFromUrl ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
            Analyze URL & clone voice
          </Button>
          {cloningFromUrl && <ProgressBar value={urlCloneProgress} stepLabel={urlCloneStep} />}
        </div>

        <div className="rounded-xl border border-border p-3 space-y-3">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
            Or train a new voice from a sample file / mic
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Name</Label>
              <Input
                value={newVoiceName}
                onChange={(e) => setNewVoiceName(e.target.value)}
                placeholder="e.g. My voice"
              />
            </div>
            <div className="space-y-2">
              <Label>Sample file</Label>
              <Input
                type="file"
                accept="audio/*,.mp3,.wav,.m4a,.webm"
                onChange={(e) => setSampleFile(e.target.files?.[0] ?? null)}
              />
            </div>
          </div>
          {sampleFile && (
            <p className="truncate text-xs text-muted-foreground">{sampleFile.name}</p>
          )}
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
            <Button type="button" size="sm" onClick={saveVoice} disabled={savingVoice || !fishOk}>
              {savingVoice ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              Save voice
            </Button>
          </div>
        </div>
      </div>

      <div className="surface-soft space-y-3 p-4">
        <p className="text-sm font-semibold">2. Text</p>
        <div className="space-y-2">
          <Label>File title</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="my-script"
          />
          <p className="text-xs text-muted-foreground">
            Saved as:{" "}
            <span className="font-semibold text-foreground">
              {(selectedVoiceName || "Voice").replace(/\s+/g, "-")} -{" "}
              {(title.trim() || "spoken").replace(/\s+/g, "-")}.mp3
            </span>
          </p>
        </div>
        <div className="space-y-2">
          <Label>Script to speak</Label>
          <textarea
            className="min-h-[180px] w-full rounded-xl border border-border bg-[var(--card)] px-3 py-2 text-sm"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste any script, hook, or narration here…"
          />
          <p className="text-xs text-muted-foreground">{text.trim().length.toLocaleString()} characters</p>
        </div>
        <Button type="button" size="lg" onClick={makeMp3} disabled={speaking || !fishOk}>
          {speaking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
          Make MP3
        </Button>
        {speaking && <ProgressBar value={progress} stepLabel={statusStep} />}
      </div>

      {(previewUrl || resultFilename) && (
        <div className="surface-soft space-y-3 p-4">
          <p className="text-sm font-semibold">3. Result</p>
          {resultFilename && (
            <p className="truncate text-sm text-muted-foreground">
              File: <span className="font-semibold text-foreground">{resultFilename}</span>
            </p>
          )}
          {previewUrl && <audio controls className="w-full" src={previewUrl} preload="metadata" />}
          {resultFilename && (
            <Button type="button" variant="secondary" onClick={handleDownload} disabled={downloading}>
              {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Download MP3
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
