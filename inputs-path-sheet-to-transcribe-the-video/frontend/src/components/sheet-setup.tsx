"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { mergeSheetHistory, readSheetCache, writeSheetCache } from "@/lib/sheet-cache";
import type { SheetHistoryItem, SheetKind, SheetSessionResponse } from "@/lib/types";
import { ExternalLink, FileSpreadsheet, Loader2, Plus, RotateCcw } from "lucide-react";

interface SheetSetupProps {
  connected: boolean;
  email?: string | null;
  onReady?: () => void;
}

function SheetCard({
  kind,
  label,
  hint,
  url,
  history,
  busy,
  onUse,
  onCreate,
}: {
  kind: SheetKind;
  label: string;
  hint: string;
  url?: string | null;
  history: SheetHistoryItem[];
  busy: boolean;
  onUse: (url: string) => Promise<void>;
  onCreate: () => Promise<void>;
}) {
  const [other, setOther] = useState(false);
  const [paste, setPaste] = useState("");
  const recents = history.filter((item) => item.url && item.url !== url);

  const submitPaste = async () => {
    if (!paste.trim()) {
      toast({ title: "Paste a Google Sheet link", variant: "destructive" });
      return;
    }
    await onUse(paste.trim());
    setPaste("");
    setOther(false);
  };

  return (
    <div className="surface-soft space-y-3 p-4">
      <div>
        <p className="text-sm font-extrabold">{label}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
      </div>

      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 truncate text-sm font-semibold text-[var(--coral)] underline-offset-2 hover:underline"
        >
          <ExternalLink className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{url}</span>
        </a>
      ) : (
        <p className="text-sm text-muted-foreground">No sheet yet — we’ll create one, or you can paste a link.</p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setOther((v) => !v)} disabled={busy}>
          <RotateCcw className="h-3.5 w-3.5" />
          {url ? "Use a different sheet" : "Choose a sheet"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCreate} disabled={busy}>
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          Create new
        </Button>
      </div>

      {other && (
        <div className="space-y-3 border-t border-border pt-3">
          {recents.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Recently used</p>
              {recents.map((item) => (
                <button
                  key={item.url}
                  type="button"
                  disabled={busy}
                  onClick={() => onUse(item.url)}
                  className="block w-full truncate rounded-xl px-3 py-2 text-left text-sm hover:bg-surface-muted"
                >
                  <span className="font-semibold">{item.title || "Google Sheet"}</span>
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground">{item.url}</span>
                </button>
              ))}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor={`${kind}-paste`}>Paste any Google Sheet URL</Label>
            <Input
              id={`${kind}-paste`}
              value={paste}
              onChange={(e) => setPaste(e.target.value)}
              placeholder="https://docs.google.com/spreadsheets/d/…"
              onKeyDown={(e) => e.key === "Enter" && submitPaste()}
            />
            <Button type="button" size="sm" onClick={submitPaste} disabled={busy} className="w-full">
              Use this sheet
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function SheetSetup({ connected, email, onReady }: SheetSetupProps) {
  const [session, setSession] = useState<SheetSessionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyKind, setBusyKind] = useState<SheetKind | "all" | null>(null);

  const persist = (next: SheetSessionResponse) => {
    setSession(next);
    if (email) writeSheetCache(email, next);
    onReady?.();
  };

  useEffect(() => {
    if (!connected || !email) return;
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      try {
        const local = readSheetCache(email);
        let remote = await api.sheetsSession();
        const inputHistory = mergeSheetHistory(remote.input_history, local.input_history);
        const outputHistory = mergeSheetHistory(remote.output_history, local.output_history);

        try {
          if (!remote.input_url && local.input_url) {
            remote = await api.sheetsUse({ kind: "input", url: local.input_url });
          }
        } catch {
          /* stale browser cache */
        }
        try {
          if (!remote.output_url && local.output_url) {
            remote = await api.sheetsUse({ kind: "output", url: local.output_url });
          }
        } catch {
          /* stale browser cache */
        }
        if (!remote.input_url || !remote.output_url) {
          remote = await api.sheetsBootstrap();
          if (remote.created_input || remote.created_output) {
            toast({
              title: "Sheets ready",
              description: "Created a new video list and/or results spreadsheet in your Google Drive.",
            });
          }
        }
        remote = {
          ...remote,
          input_history: mergeSheetHistory(remote.input_history, inputHistory),
          output_history: mergeSheetHistory(remote.output_history, outputHistory),
        };
        if (!cancelled) persist(remote);
      } catch (err) {
        if (!cancelled) {
          toast({
            title: "Couldn’t load sheets",
            description: err instanceof Error ? err.message : "Try connecting Google again.",
            variant: "destructive",
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
    // persist/onReady change every render; only reconnect when Google identity changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, email]);

  const handleUse = async (kind: SheetKind, url: string) => {
    setBusyKind(kind);
    try {
      const next = await api.sheetsUse({ kind, url });
      persist(next);
      toast({ title: kind === "input" ? "Video list updated" : "Results sheet updated" });
    } catch (err) {
      toast({
        title: "Couldn’t use that sheet",
        description: err instanceof Error ? err.message : "Check the link and sharing.",
        variant: "destructive",
      });
    } finally {
      setBusyKind(null);
    }
  };

  const handleCreate = async (kind: SheetKind) => {
    setBusyKind(kind);
    try {
      const next = await api.sheetsCreate(kind);
      persist(next);
      toast({ title: "New spreadsheet created in Drive" });
    } catch (err) {
      toast({
        title: "Couldn’t create a sheet",
        description: err instanceof Error ? err.message : "Try again",
        variant: "destructive",
      });
    } finally {
      setBusyKind(null);
    }
  };

  if (!connected) {
    return (
      <div className="surface p-5">
        <h3 className="text-lg font-extrabold tracking-tight">Your Google Sheets</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect Google first. We’ll reuse your last sheets, or create new ones automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="surface overflow-hidden">
      <div className="flex items-start gap-3 px-4 py-4 sm:px-5">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--coral)_16%,transparent)] text-[var(--coral)]">
          {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <FileSpreadsheet className="h-5 w-5" />}
        </span>
        <div className="min-w-0">
          <p className="text-base font-extrabold tracking-tight">Your Google Sheets</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {loading
              ? "Checking recently used sheets…"
              : "Starts from your last sheets. Switch anytime — nothing is hardcoded."}
          </p>
        </div>
      </div>

      <div className="space-y-3 border-t border-border px-4 pb-5 pt-4 sm:px-5">
        <SheetCard
          kind="input"
          label="Video list (input)"
          hint="Where video names and links live"
          url={session?.input_url}
          history={session?.input_history || []}
          busy={busyKind === "input" || busyKind === "all" || loading}
          onUse={(url) => handleUse("input", url)}
          onCreate={() => handleCreate("input")}
        />
        <SheetCard
          kind="output"
          label="Transcripts (output)"
          hint="Where finished scripts are saved"
          url={session?.output_url}
          history={session?.output_history || []}
          busy={busyKind === "output" || busyKind === "all" || loading}
          onUse={(url) => handleUse("output", url)}
          onCreate={() => handleCreate("output")}
        />
      </div>
    </div>
  );
}
