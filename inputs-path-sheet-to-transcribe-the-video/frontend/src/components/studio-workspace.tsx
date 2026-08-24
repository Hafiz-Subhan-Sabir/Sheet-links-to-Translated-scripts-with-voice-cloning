"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ProgressBar } from "@/components/progress-bar";
import { toast } from "@/hooks/use-toast";
import { api, waitForJob } from "@/lib/api";
import { normalizeProgress } from "@/lib/progress";
import type { WorkflowId } from "@/components/mode-chooser";
import type { AutoEditPackResult, JobStatusResponse } from "@/lib/types";
import { Check, Clapperboard, Copy, Download, Film, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface StudioWorkspaceProps {
  mode: Extract<WorkflowId, "original" | "viral" | "shorts">;
  onBack: () => void;
}

function parseUrls(raw: string): string[] {
  return raw
    .split(/[\n,\s]+/)
    .map((u) => u.trim())
    .filter((u) => /^https?:\/\//i.test(u));
}

function extractScript(markdown: string): string {
  const fenced = markdown.match(/```(?:SCRIPT|script)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]?.trim()) return fenced[1].trim();
  const after = markdown.split(/##\s*SCRIPT\s*/i)[1];
  if (!after) return markdown;
  const next = after.split(/\n##\s+/)[0];
  return next.replace(/^```[\w]*\n?/, "").replace(/\n?```$/, "").trim() || markdown;
}

function editDownloadUrl(filename: string, inline = false) {
  const base = `${API_URL}/api/edit/download/${encodeURIComponent(filename)}`;
  return inline ? `${base}?inline=1` : base;
}

async function saveEditFile(filename: string) {
  const res = await fetch(editDownloadUrl(filename, false));
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

export function StudioWorkspace({ mode, onBack }: StudioWorkspaceProps) {
  const [idea, setIdea] = useState("");
  const [format, setFormat] = useState<"long" | "short">("long");
  const [urlsText, setUrlsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [markdown, setMarkdown] = useState("");
  const [copied, setCopied] = useState(false);
  const [buildingEdit, setBuildingEdit] = useState(false);
  const [editProgress, setEditProgress] = useState(0);
  const [editStep, setEditStep] = useState("");
  const [editPack, setEditPack] = useState<AutoEditPackResult | null>(null);
  const [videos, setVideos] = useState<
    { title: string; view_count: number; url: string; channel?: string; views_per_day?: number | null }[]
  >([]);

  const meta = useMemo(() => {
    if (mode === "original") {
      return {
        title: "New video script",
        blurb: "One idea → titles, hook, and a ready-to-record script.",
        cta: "Generate",
      };
    }
    if (mode === "viral") {
      return {
        title: "Viral compare → new video",
        blurb: "Paste 5–10 same-niche links. Get patterns + an original script you can film.",
        cta: "Analyze",
      };
    }
    return {
      title: "Shorts blueprint",
      blurb: "Paste viral Shorts. Get hook, body, ending, and a 30–55s script.",
      cta: "Build Short",
    };
  }, [mode]);

  const run = async () => {
    setLoading(true);
    setMarkdown("");
    setVideos([]);
    setCopied(false);
    setEditPack(null);
    try {
      if (mode === "original") {
        if (!idea.trim()) {
          toast({ title: "Add your idea", variant: "destructive" });
          return;
        }
        const res = await api.studioOriginal({
          topic: idea.trim(),
          format_hint: format === "short" ? "YouTube Shorts" : "long-form YouTube video",
          length_minutes: format === "short" ? 1 : 8,
        });
        setMarkdown(res.markdown);
      } else {
        const urls = parseUrls(urlsText);
        if (urls.length < 3) {
          toast({
            title: "Need 3+ links",
            description: "Paste at least 3 YouTube URLs (best with 5–10).",
            variant: "destructive",
          });
          return;
        }
        const res =
          mode === "viral" ? await api.studioViral({ urls }) : await api.studioShorts({ urls });
        setMarkdown(res.markdown);
        setVideos(res.videos || []);
      }
      toast({ title: "Ready to film", description: "Copy the SCRIPT block and record." });
    } catch (err) {
      toast({
        title: "Couldn’t finish",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const copyScript = async () => {
    const text = extractScript(markdown);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast({ title: "Script copied" });
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ title: "Copy failed", variant: "destructive" });
    }
  };

  const buildEditPack = async () => {
    const script = extractScript(markdown);
    if (script.trim().length < 20) {
      toast({ title: "Script too short for visuals", variant: "destructive" });
      return;
    }
    setBuildingEdit(true);
    setEditProgress(0);
    setEditStep("Starting…");
    setEditPack(null);
    try {
      const start = await api.editAutoPack({
        script,
        title: mode === "shorts" ? "shorts-edit" : "studio-edit",
        generate_images: true,
        build_video: true,
      });
      const finalStatus = await waitForJob(
        start.job_id,
        (status: JobStatusResponse) => {
          setEditStep(status.step || "Building visuals…");
          setEditProgress(normalizeProgress(status.progress));
        },
        2000,
        45 * 60 * 1000
      );
      const result = (finalStatus.result || {}) as AutoEditPackResult;
      if (!result.zip_filename) {
        throw new Error("Edit pack finished but zip was missing");
      }
      setEditPack(result);
      toast({
        title: "Visual edit pack ready",
        description: `${result.beat_count} beats · zip + rough cut downloaded from Speak/Studio.`,
      });
    } catch (err) {
      toast({
        title: "Visual edit failed",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setBuildingEdit(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight sm:text-2xl">{meta.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{meta.blurb}</p>
        </div>
        <Button type="button" variant="outline" onClick={onBack}>
          All workflows
        </Button>
      </div>

      <div className="surface-soft space-y-3 p-4">
        {mode === "original" ? (
          <>
            <div className="space-y-2">
              <Label>What’s the video about?</Label>
              <textarea
                className="min-h-[88px] w-full rounded-xl border border-border bg-[var(--card)] px-3 py-2 text-sm"
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                placeholder="e.g. I tried living on $20/day for a week — what actually broke my budget"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void run();
                }}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["long", "Long video"],
                  ["short", "Shorts"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-bold",
                    format === id
                      ? "border-[var(--coral)] bg-[color-mix(in_srgb,var(--coral)_16%,transparent)]"
                      : "border-border text-muted-foreground"
                  )}
                  onClick={() => setFormat(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="space-y-2">
            <Label>Paste 5–10 YouTube links</Label>
            <textarea
              className="min-h-[130px] w-full rounded-xl border border-border bg-[var(--card)] px-3 py-2 text-sm"
              value={urlsText}
              onChange={(e) => setUrlsText(e.target.value)}
              placeholder={"https://youtube.com/watch?v=...\nhttps://youtube.com/shorts/..."}
            />
            <p className="text-xs text-muted-foreground">
              Same niche works best. Niche is inferred — no extra fields.
            </p>
          </div>
        )}

        <Button type="button" size="lg" onClick={run} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {loading ? "Working…" : meta.cta}
        </Button>
      </div>

      {videos.length > 0 && (
        <div className="surface-soft space-y-2 p-4">
          <p className="text-sm font-semibold">Ranked references</p>
          <ul className="space-y-1 text-sm">
            {videos.map((v) => (
              <li key={v.url} className="flex flex-wrap gap-x-2">
                <span className="font-medium">{v.view_count.toLocaleString()} views</span>
                {v.views_per_day != null && (
                  <span className="text-muted-foreground">
                    · {Math.round(v.views_per_day).toLocaleString()}/day
                  </span>
                )}
                <a className="hover:underline" href={v.url} target="_blank" rel="noreferrer">
                  {v.title || v.url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {markdown && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={copyScript}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? "Copied" : "Copy SCRIPT"}
            </Button>
            <Button type="button" onClick={buildEditPack} disabled={buildingEdit}>
              {buildingEdit ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
              Suggest visuals &amp; edit pack
            </Button>
          </div>
          {buildingEdit && <ProgressBar value={editProgress} stepLabel={editStep} />}
          {editPack && (
            <div className="surface-soft space-y-3 p-4">
              <p className="text-sm font-semibold">{editPack.beat_count} timed visual beats</p>
              <p className="text-xs text-muted-foreground">{editPack.capcut_note}</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => void saveEditFile(editPack.zip_filename)}
                >
                  <Download className="h-4 w-4" />
                  Download edit pack (.zip)
                </Button>
                {editPack.mp4_filename && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void saveEditFile(editPack.mp4_filename!)}
                  >
                    <Film className="h-4 w-4" />
                    Download rough MP4
                  </Button>
                )}
              </div>
              {editPack.mp4_filename && (
                <video
                  controls
                  className="w-full rounded-xl border border-border"
                  src={editDownloadUrl(editPack.mp4_filename, true)}
                  preload="metadata"
                />
              )}
            </div>
          )}
          <article className="surface-soft whitespace-pre-wrap p-4 text-sm leading-relaxed">
            {markdown}
          </article>
        </div>
      )}
    </div>
  );
}
