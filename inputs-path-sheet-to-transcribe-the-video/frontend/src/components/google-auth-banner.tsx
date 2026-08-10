"use client";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "@/hooks/use-toast";
import { CheckCircle2, LogOut, Mail, Zap } from "lucide-react";

interface GoogleAuthBannerProps {
  connected: boolean;
  email?: string | null;
  sheetReady?: boolean;
  sheetUrl?: string | null;
  oauthConfigured?: boolean;
  onStatusChange: () => void;
}

export function GoogleAuthBanner({
  connected,
  email,
  sheetReady,
  sheetUrl,
  oauthConfigured = true,
  onStatusChange,
}: GoogleAuthBannerProps) {
  const handleConnect = () => {
    if (!oauthConfigured) {
      toast({
        title: "Google OAuth not set up yet",
        description:
          "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env, restart backend, then try again.",
        variant: "destructive",
      });
      return;
    }
    window.location.href = api.googleAuthUrl();
  };

  const handleDisconnect = async () => {
    try {
      await api.disconnectGoogle();
      toast({ title: "Disconnected" });
      onStatusChange();
    } catch (e) {
      toast({
        title: "Error",
        description: e instanceof Error ? e.message : "Failed",
        variant: "destructive",
      });
    }
  };

  if (!connected) {
    return (
      <div
        className="surface overflow-hidden p-5"
        style={{
          background:
            "linear-gradient(135deg, color-mix(in srgb, var(--coral) 18%, var(--card)) 0%, var(--card) 60%)",
        }}
      >
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--coral)] text-white">
          <Zap className="h-5 w-5" />
        </div>
        <h3 className="text-lg font-extrabold tracking-tight">Connect Google</h3>
        <p className="mt-1 text-sm text-muted-foreground">One click for Sheets and Docs access.</p>
        {!oauthConfigured && (
          <p className="mt-3 rounded-xl bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] px-3 py-2 text-sm text-[var(--warn)]">
            Missing OAuth keys. Create a Google Cloud Desktop/Web client for{" "}
            <strong>one Gmail</strong>, put <code className="text-xs">GOOGLE_CLIENT_ID</code> +{" "}
            <code className="text-xs">GOOGLE_CLIENT_SECRET</code> in{" "}
            <code className="text-xs">backend/.env</code>, add redirect{" "}
            <code className="text-xs">http://localhost:8000/api/auth/google/callback</code>, add
            yourself as a Test user, then restart the backend.
          </p>
        )}
        <Button onClick={handleConnect} size="lg" className="mt-4 w-full" disabled={!oauthConfigured}>
          Continue with Google
        </Button>
      </div>
    );
  }

  return (
    <div className="surface flex items-center justify-between gap-3 p-4">
      <div className="min-w-0">
        <p className="flex items-center gap-2 truncate text-sm font-bold">
          <Mail className="h-4 w-4 shrink-0 text-[var(--coral)]" />
          <span className="truncate">{email}</span>
        </p>
        {sheetReady ? (
          <p className="mt-1 flex items-center gap-1.5 text-xs font-semibold text-[var(--volt)]">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Ready to run
            {sheetUrl && (
              <a href={sheetUrl} target="_blank" rel="noopener noreferrer" className="underline opacity-80">
                input
              </a>
            )}
          </p>
        ) : (
          <p className="mt-1 text-xs text-muted-foreground">Open “Your Google Sheets” to finish setup</p>
        )}
      </div>
      <Button variant="outline" size="sm" onClick={handleDisconnect}>
        <LogOut className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
