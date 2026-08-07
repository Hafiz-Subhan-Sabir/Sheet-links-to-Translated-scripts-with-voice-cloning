"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { ChevronDown, FolderOpen, Loader2, Lock, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface AdminSectionProps {
  onSaved?: () => void;
  /** Open the panel by default when sheets still need setup */
  defaultOpen?: boolean;
}

export function AdminSection({ onSaved, defaultOpen }: AdminSectionProps) {
  const [open, setOpen] = useState(!!defaultOpen);
  const [configured, setConfigured] = useState(false);
  const [outputConfigured, setOutputConfigured] = useState(false);
  const [locked, setLocked] = useState(true);
  const [password, setPassword] = useState("");
  const [sheetUrl, setSheetUrl] = useState("");
  const [outputSheetUrl, setOutputSheetUrl] = useState("");
  const [docsFolderId, setDocsFolderId] = useState("");
  const [voiceOutputDir, setVoiceOutputDir] = useState("");
  const [loading, setLoading] = useState(false);
  const [unlocking, setUnlocking] = useState(false);

  const bothReady = configured && outputConfigured;

  const loadStatus = async () => {
    try {
      const status = await api.adminConfigStatus();
      setConfigured(status.configured);
      setOutputConfigured(!!status.output_configured);
      setLocked(status.locked);
      if (!status.locked) {
        setSheetUrl(status.sheet_url || "");
        setOutputSheetUrl(status.output_sheet_url || "");
        setDocsFolderId(status.docs_folder_id || "");
        setVoiceOutputDir(status.voice_output_dir || "");
      }
      // Keep open until both sheets are saved
      if (!status.configured || !status.output_configured) {
        setOpen(true);
      }
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);

  const handleUnlock = async () => {
    setUnlocking(true);
    try {
      const result = await api.adminUnlock(password);
      if (!result.success) {
        toast({ title: "That password didn’t work", variant: "destructive" });
        return;
      }
      setPassword("");
      await loadStatus();
      toast({ title: "Unlocked", description: "You can update your sheet links now." });
    } catch (err) {
      toast({
        title: "Couldn’t unlock",
        description: err instanceof Error ? err.message : "Try again",
        variant: "destructive",
      });
    } finally {
      setUnlocking(false);
    }
  };

  const handleSave = async () => {
    if (!sheetUrl.trim() || !outputSheetUrl.trim()) {
      toast({
        title: "Almost there",
        description: "Add both spreadsheet links before saving.",
        variant: "destructive",
      });
      return;
    }
    setLoading(true);
    try {
      await api.saveAdminConfig({
        sheet_url: sheetUrl.trim(),
        output_sheet_url: outputSheetUrl.trim(),
        docs_folder_id: docsFolderId.trim() || undefined,
        voice_output_dir: voiceOutputDir.trim() || undefined,
      });
      toast({ title: "Saved", description: "Your sheets are linked. You’re ready to run." });
      setSheetUrl("");
      setOutputSheetUrl("");
      setDocsFolderId("");
      setVoiceOutputDir("");
      await loadStatus();
      setOpen(false);
      onSaved?.();
    } catch (err) {
      toast({
        title: "Couldn’t save",
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleLock = async () => {
    try {
      await api.adminLock();
      setLocked(true);
      setSheetUrl("");
      setOutputSheetUrl("");
      await loadStatus();
      toast({ title: "Locked again" });
    } catch (err) {
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "Failed",
        variant: "destructive",
      });
    }
  };

  const statusLabel = bothReady
    ? "Both sheets linked"
    : configured || outputConfigured
      ? "One sheet still missing"
      : "Not set up yet";

  return (
    <div className="surface overflow-hidden">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-4 text-left transition hover:bg-surface-muted sm:px-5"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--coral)_16%,transparent)] text-[var(--coral)]">
          <Settings2 className="h-5 w-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-base font-extrabold tracking-tight">Your Google Sheets</span>
          <span className="mt-0.5 block truncate text-sm text-muted-foreground">{statusLabel}</span>
        </span>
        <ChevronDown
          className={cn(
            "h-5 w-5 shrink-0 text-muted-foreground transition-transform duration-200",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div className="space-y-4 border-t border-border px-4 pb-5 pt-4 sm:px-5">
          <p className="text-sm text-muted-foreground">
            Tell the app where your videos are listed, and where to save the finished transcripts.
          </p>

          {locked ? (
            <div className="space-y-4">
              {(configured || outputConfigured) && (
                <div className="surface-soft space-y-1.5 p-3 text-sm">
                  <p className="font-semibold">
                    {configured ? "✓ Video list sheet is saved" : "○ Video list sheet not added yet"}
                  </p>
                  <p className="font-semibold">
                    {outputConfigured
                      ? "✓ Results sheet is saved"
                      : "○ Results sheet not added yet"}
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="admin-password">Password to edit settings</Label>
                <Input
                  id="admin-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your admin password"
                  onKeyDown={(e) => e.key === "Enter" && handleUnlock()}
                />
              </div>

              <Button
                onClick={handleUnlock}
                disabled={unlocking || !password}
                className="w-full"
                size="lg"
              >
                {unlocking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
                Unlock settings
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="sheet-url">Where are your videos listed?</Label>
                <Input
                  id="sheet-url"
                  value={sheetUrl}
                  onChange={(e) => setSheetUrl(e.target.value)}
                  placeholder="Paste the Google Sheet link for your video list"
                  autoFocus
                />
                <p className="text-xs text-muted-foreground">
                  This sheet should have video names, links, and a status column.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="output-sheet-url">Where should we save the transcripts?</Label>
                <Input
                  id="output-sheet-url"
                  value={outputSheetUrl}
                  onChange={(e) => setOutputSheetUrl(e.target.value)}
                  placeholder="Paste a different Google Sheet link for results"
                />
                <p className="text-xs text-muted-foreground">
                  Use a separate spreadsheet so your results stay organized.
                </p>
              </div>

              <details className="surface-soft p-3">
                <summary className="cursor-pointer text-sm font-bold">More options</summary>
                <div className="mt-3 space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="folder-id">Google Drive folder for documents (optional)</Label>
                    <Input
                      id="folder-id"
                      value={docsFolderId}
                      onChange={(e) => setDocsFolderId(e.target.value)}
                      placeholder="Folder ID from Drive, if you want Docs saved there"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="voice-dir">Folder for cloned voice files (optional)</Label>
                    <div className="relative">
                      <FolderOpen className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="voice-dir"
                        className="pl-9"
                        value={voiceOutputDir}
                        onChange={(e) => setVoiceOutputDir(e.target.value)}
                        placeholder="e.g. C:\Voices\output"
                      />
                    </div>
                  </div>
                </div>
              </details>

              <div className="flex flex-wrap gap-2 pt-1">
                <Button onClick={handleSave} disabled={loading} className="flex-1" size="lg">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Save my sheets
                </Button>
                <Button variant="outline" onClick={handleLock}>
                  Lock
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
