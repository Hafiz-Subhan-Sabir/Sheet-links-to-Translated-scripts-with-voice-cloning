"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { FolderOpen, Loader2, Lock } from "lucide-react";

interface AdminSectionProps {
  onSaved?: () => void;
}

export function AdminSection({ onSaved }: AdminSectionProps) {
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
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleUnlock = async () => {
    setUnlocking(true);
    try {
      const result = await api.adminUnlock(password);
      if (!result.success) {
        toast({ title: "Wrong password", variant: "destructive" });
        return;
      }
      setPassword("");
      await loadStatus();
    } catch (err) {
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "Unlock failed",
        variant: "destructive",
      });
    } finally {
      setUnlocking(false);
    }
  };

  const handleSave = async () => {
    if (!sheetUrl.trim() || !outputSheetUrl.trim()) {
      toast({ title: "Paste both sheet links", variant: "destructive" });
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
      toast({ title: "Saved — you're ready to run" });
      setSheetUrl("");
      setOutputSheetUrl("");
      setDocsFolderId("");
      setVoiceOutputDir("");
      await loadStatus();
      onSaved?.();
    } catch (err) {
      toast({
        title: "Save failed",
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
    } catch (err) {
      toast({ title: "Error", description: err instanceof Error ? err.message : "Failed", variant: "destructive" });
    }
  };

  return (
    <div className="surface flex h-full flex-col p-5">
      <div className="mb-4">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--coral)]">Sheet links</p>
        <h3 className="mt-1 text-xl font-extrabold tracking-tight">Paste & go</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Input = video queue. Output = transcripts (different sheet).
        </p>
      </div>

      {locked ? (
        <div className="flex flex-1 flex-col gap-4">
          {(configured || outputConfigured) && (
            <div className="surface-soft space-y-1 p-3 text-sm">
              <p className="font-semibold">{configured ? "✓ Input saved" : "○ Input missing"}</p>
              <p className="font-semibold">{outputConfigured ? "✓ Output saved" : "○ Output missing"}</p>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="admin-password">Admin password</Label>
            <Input
              id="admin-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Unlock to edit links"
              onKeyDown={(e) => e.key === "Enter" && handleUnlock()}
            />
          </div>
          <Button onClick={handleUnlock} disabled={unlocking || !password} className="mt-auto w-full" size="lg">
            {unlocking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
            Unlock
          </Button>
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="sheet-url">Input sheet URL</Label>
            <Input
              id="sheet-url"
              value={sheetUrl}
              onChange={(e) => setSheetUrl(e.target.value)}
              placeholder="https://docs.google.com/spreadsheets/d/…"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="output-sheet-url">Output sheet URL</Label>
            <Input
              id="output-sheet-url"
              value={outputSheetUrl}
              onChange={(e) => setOutputSheetUrl(e.target.value)}
              placeholder="Different spreadsheet URL"
            />
          </div>

          <details className="surface-soft p-3">
            <summary className="cursor-pointer text-sm font-bold">Optional</summary>
            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="folder-id">Docs folder ID</Label>
                <Input
                  id="folder-id"
                  value={docsFolderId}
                  onChange={(e) => setDocsFolderId(e.target.value)}
                  placeholder="Optional"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="voice-dir">Voice folder</Label>
                <div className="relative">
                  <FolderOpen className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="voice-dir"
                    className="pl-9"
                    value={voiceOutputDir}
                    onChange={(e) => setVoiceOutputDir(e.target.value)}
                    placeholder="C:\Voices\output"
                  />
                </div>
              </div>
            </div>
          </details>

          <div className="mt-auto flex gap-2 pt-2">
            <Button onClick={handleSave} disabled={loading} className="flex-1" size="lg">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save & continue
            </Button>
            <Button variant="outline" onClick={handleLock}>
              Lock
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
