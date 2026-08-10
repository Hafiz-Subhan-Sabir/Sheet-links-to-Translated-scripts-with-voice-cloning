"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminSection } from "@/components/admin-section";
import { BatchWorkspace } from "@/components/batch-workspace";
import { VoiceClonePanel } from "@/components/voice-clone-panel";
import { GoogleAuthBanner } from "@/components/google-auth-banner";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { ArrowRight, Clapperboard, Mic2, Sparkles, Zap } from "lucide-react";

type TabId = "setup" | "transcribe" | "voice";

const TABS: { id: TabId; label: string }[] = [
  { id: "setup", label: "Setup" },
  { id: "transcribe", label: "Run" },
  { id: "voice", label: "Voice" },
];

export default function Dashboard() {
  const [connected, setConnected] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [oauthConfigured, setOauthConfigured] = useState(false);
  const [sheetConfigured, setSheetConfigured] = useState(false);
  const [outputConfigured, setOutputConfigured] = useState(false);
  const [inputSheetUrl, setInputSheetUrl] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("setup");
  const [userPickedTab, setUserPickedTab] = useState(false);

  const sheetsReady = sheetConfigured && outputConfigured;
  const setupDone = connected && sheetsReady;
  const canTranscribe = setupDone;
  const canVoice = connected && outputConfigured;

  const refreshAuth = useCallback(async () => {
    try {
      const [status, batchCfg] = await Promise.all([api.authStatus(), api.batchConfig()]);
      setConnected(status.connected);
      setEmail(status.email ?? null);
      setOauthConfigured(!!status.oauth_configured);
      setSheetConfigured(batchCfg.input_sheet_configured);
      setOutputConfigured(!!batchCfg.output_sheet_configured);
      setInputSheetUrl(status.sheet_url ?? null);
    } catch {
      setConnected(false);
      setOauthConfigured(false);
    }
  }, []);

  useEffect(() => {
    refreshAuth();
    const params = new URLSearchParams(window.location.search);
    if (params.get("auth") === "success") {
      toast({ title: "Google connected", description: "Paste your sheet links — almost there." });
      window.history.replaceState({}, "", "/");
      refreshAuth();
    } else if (params.get("auth") === "error") {
      toast({
        title: "Google login failed",
        description: decodeURIComponent(params.get("message") || "Try again."),
        variant: "destructive",
      });
      window.history.replaceState({}, "", "/");
    }
  }, [refreshAuth]);

  // Auto-advance: setup → run when ready (unless user chose a tab)
  useEffect(() => {
    if (userPickedTab) return;
    if (!setupDone) setTab("setup");
    else setTab("transcribe");
  }, [setupDone, userPickedTab]);

  const selectTab = (id: TabId) => {
    if (id === "transcribe" && !canTranscribe) return;
    if (id === "voice" && !canVoice) return;
    setUserPickedTab(true);
    setTab(id);
  };

  const nextAction = useMemo(() => {
    if (!connected) {
      if (!oauthConfigured) {
        return {
          label: "Next step",
          title:
            "Add GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET to backend/.env (one Gmail), restart backend, then connect",
          cta: null as string | null,
          onClick: null as (() => void) | null,
        };
      }
      return {
        label: "Next step",
        title: "Connect your Google account so we can use Sheets and Docs",
        cta: "Connect Google",
        onClick: () => {
          window.location.href = api.googleAuthUrl();
        },
      };
    }
    if (!sheetsReady) {
      return {
        label: "Next step",
        title: "Open “Your Google Sheets” below, unlock, and paste both spreadsheet links",
        cta: null as string | null,
        onClick: null as (() => void) | null,
      };
    }
    if (tab === "setup") {
      return {
        label: "You’re set",
        title: "Everything’s linked — start processing your videos",
        cta: "Start processing",
        onClick: () => selectTab("transcribe"),
      };
    }
    if (tab === "transcribe") {
      return {
        label: "What’s next",
        title: "When processing finishes, clone voices or mark items done",
        cta: "Go to Voice",
        onClick: () => selectTab("voice"),
      };
    }
    return {
      label: "Finish up",
      title: "Choose a voice, pick transcripts, then clone — or mark them done",
      cta: null,
      onClick: null,
    };
  }, [connected, oauthConfigured, sheetsReady, tab]);

  return (
    <div className="app-viewport">
      <div className="app-shell animate-fade-in-up">
        <header className="flex shrink-0 items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-5 sm:py-3">
          <div className="min-w-0 flex-1">
            <p className="brand-mark">
              Volt<span>Script</span>
            </p>
            <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
              <span className="pulse-dot" />
              Sheet → translate → voice
            </p>
          </div>

          <nav className="rail hidden sm:flex" aria-label="Steps">
            {TABS.map((t) => {
              const locked =
                (t.id === "transcribe" && !canTranscribe) || (t.id === "voice" && !canVoice);
              return (
                <button
                  key={t.id}
                  type="button"
                  className="rail-btn"
                  data-active={tab === t.id}
                  disabled={locked}
                  onClick={() => selectTab(t.id)}
                >
                  {t.id === "setup" && <Zap className="h-3.5 w-3.5" />}
                  {t.id === "transcribe" && <Clapperboard className="h-3.5 w-3.5" />}
                  {t.id === "voice" && <Mic2 className="h-3.5 w-3.5" />}
                  {t.label}
                </button>
              );
            })}
          </nav>

          <ThemeToggle />
        </header>

        <div className="flex shrink-0 gap-1 overflow-x-auto px-3 pb-2 sm:hidden">
          {TABS.map((t) => {
            const locked =
              (t.id === "transcribe" && !canTranscribe) || (t.id === "voice" && !canVoice);
            return (
              <button
                key={t.id}
                type="button"
                className="rail-btn shrink-0"
                data-active={tab === t.id}
                disabled={locked}
                onClick={() => selectTab(t.id)}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="scroll-pane min-h-0 flex-1 px-3 py-2.5 sm:px-5 sm:py-3">
          {tab === "setup" && (
            <div className="mx-auto grid max-w-5xl gap-3 lg:grid-cols-[1.05fr_1fr] lg:gap-4">
              <section className="space-y-4">
                <div>
                  <p className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-[color-mix(in_srgb,var(--volt)_35%,transparent)] bg-[color-mix(in_srgb,var(--volt)_12%,transparent)] px-3 py-1 text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--volt)]">
                    <Sparkles className="h-3 w-3" />
                    2-minute setup
                  </p>
                  <h2 className="hero-blurb">
                    Sign in once.
                    <br />
                    Add your sheets.
                    <br />
                    <span style={{ color: "var(--coral)" }}>Start processing.</span>
                  </h2>
                </div>

                <ol className="space-y-2">
                  {[
                    { n: "1", ok: connected, t: "Google account", d: email || "Not connected yet" },
                    {
                      n: "2",
                      ok: sheetConfigured,
                      t: "Video list sheet",
                      d: "Where your video links live",
                    },
                    {
                      n: "3",
                      ok: outputConfigured,
                      t: "Results sheet",
                      d: "Where transcripts get saved",
                    },
                  ].map((s) => (
                    <li key={s.n} className="checklist-item">
                      <span
                        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-extrabold"
                        style={{
                          background: s.ok ? "var(--volt)" : "var(--surface-muted)",
                          color: s.ok ? "#1a0804" : "var(--muted-foreground)",
                        }}
                      >
                        {s.ok ? "✓" : s.n}
                      </span>
                      <div>
                        <p className="font-bold">{s.t}</p>
                        <p className="text-xs text-muted-foreground">{s.d}</p>
                      </div>
                    </li>
                  ))}
                </ol>

                <GoogleAuthBanner
                  connected={connected}
                  email={email}
                  sheetReady={sheetsReady}
                  sheetUrl={inputSheetUrl}
                  oauthConfigured={oauthConfigured}
                  onStatusChange={refreshAuth}
                />
              </section>

              <AdminSection
                defaultOpen={!sheetsReady}
                onSaved={() => {
                  refreshAuth();
                  setUserPickedTab(false);
                }}
              />
            </div>
          )}

          {tab === "transcribe" && (
            <div className="mx-auto h-full max-w-5xl">
              <BatchWorkspace
                connected={connected}
                sheetConfigured={sheetConfigured}
                outputConfigured={outputConfigured}
                inputSheetUrl={inputSheetUrl}
                onStepChange={() => {}}
                onOpenVoice={() => selectTab("voice")}
              />
            </div>
          )}

          {tab === "voice" && (
            <div className="mx-auto h-full max-w-5xl">
              <VoiceClonePanel connected={connected} outputConfigured={outputConfigured} />
            </div>
          )}
        </div>

        <div className="next-bar shrink-0">
          <div className="min-w-0 flex-1">
            <p className="next-bar__label">{nextAction.label}</p>
            <p className="truncate text-sm font-semibold sm:text-base">{nextAction.title}</p>
          </div>
          {nextAction.cta && nextAction.onClick && (
            <Button size="default" onClick={nextAction.onClick} className="shrink-0 sm:h-11 sm:px-8 sm:text-base">
              {nextAction.cta}
              <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
