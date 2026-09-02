"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminSection } from "@/components/admin-section";
import { BatchWorkspace } from "@/components/batch-workspace";
import { ModeChooser, type WorkflowId } from "@/components/mode-chooser";
import { ProspectWorkspace } from "@/components/prospect-workspace";
import { SalesWorkspace } from "@/components/sales-workspace";
import { SpeakWorkspace } from "@/components/speak-workspace";
import { StudioWorkspace } from "@/components/studio-workspace";
import { VoiceClonePanel } from "@/components/voice-clone-panel";
import { GoogleAuthBanner } from "@/components/google-auth-banner";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { ArrowRight, Clapperboard, Home, MessageCircle, Mic2, Search, Sparkles, Zap } from "lucide-react";

type TabId = "setup" | "home" | "transcribe" | "studio" | "speak" | "sales" | "prospect" | "voice";

const TABS: { id: TabId; label: string }[] = [
  { id: "setup", label: "Setup" },
  { id: "home", label: "Home" },
  { id: "transcribe", label: "Run" },
  { id: "studio", label: "Studio" },
  { id: "speak", label: "Speak" },
  { id: "sales", label: "Sales" },
  { id: "prospect", label: "Prospect" },
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
  const [workflow, setWorkflow] = useState<WorkflowId | null>(null);

  const sheetsReady = sheetConfigured && outputConfigured;
  const setupDone = connected && sheetsReady;
  const canTranscribe = setupDone;
  const canVoice = connected && outputConfigured;
  const canHome = connected;

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

  // After Google connect → Home (mode chooser). Sheets only required for Run/transcribe.
  useEffect(() => {
    if (userPickedTab) return;
    if (!connected) setTab("setup");
    else setTab("home");
  }, [connected, userPickedTab]);

  const selectTab = (id: TabId) => {
    if (id === "home" && !canHome) return;
    if (id === "transcribe" && !canTranscribe) return;
    if (id === "voice" && !canVoice) return;
    if (id === "studio" && !connected) return;
    if (id === "speak" && !connected) return;
    if (id === "sales" && !connected) return;
    if (id === "prospect" && !connected) return;
    setUserPickedTab(true);
    setTab(id);
  };

  const chooseWorkflow = (id: WorkflowId) => {
    setWorkflow(id);
    setUserPickedTab(true);
    if (id === "transcribe") setTab("transcribe");
    else if (id === "speak") setTab("speak");
    else if (id === "sales") setTab("sales");
    else if (id === "prospect") setTab("prospect");
    else setTab("studio");
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
    if (tab === "setup" && !sheetsReady) {
      return {
        label: "Next step",
        title: "For sheet transcription: unlock “Your Google Sheets” and paste both links",
        cta: "Choose workflow",
        onClick: () => selectTab("home"),
      };
    }
    if (tab === "setup") {
      return {
        label: "You’re set",
        title: "Pick a workflow on Home — transcribe, original, viral, or Shorts",
        cta: "Choose workflow",
        onClick: () => selectTab("home"),
      };
    }
    if (tab === "home") {
      return {
        label: "Your move",
        title: "Tap a numbered path — each one says what you’ll get",
        cta: null,
        onClick: null,
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
    if (tab === "studio") {
      return {
        label: "Studio",
        title: "Use the brief as a starting point — then script, film, or voice-clone your own take",
        cta: "All workflows",
        onClick: () => selectTab("home"),
      };
    }
    return {
      label: "Finish up",
      title: "Save voice → Speak selected text (ready rows auto-select after save)",
      cta: null,
      onClick: null,
    };
  }, [connected, oauthConfigured, sheetsReady, tab]);

  const tabLocked = (id: TabId) =>
    (id === "home" && !canHome) ||
    (id === "transcribe" && !canTranscribe) ||
    (id === "voice" && !canVoice) ||
    (id === "studio" && !connected) ||
    (id === "speak" && !connected) ||
    (id === "sales" && !connected) ||
    (id === "prospect" && !connected);

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
              Sheet → studio → voice
            </p>
          </div>

          <nav className="rail hidden sm:flex" aria-label="Steps">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className="rail-btn"
                data-tab={t.id}
                data-active={tab === t.id}
                disabled={tabLocked(t.id)}
                onClick={() => selectTab(t.id)}
              >
                {t.id === "setup" && <Zap className="h-3.5 w-3.5" />}
                {t.id === "home" && <Home className="h-3.5 w-3.5" />}
                {t.id === "transcribe" && <Clapperboard className="h-3.5 w-3.5" />}
                {t.id === "studio" && <Sparkles className="h-3.5 w-3.5" />}
                {t.id === "speak" && <Mic2 className="h-3.5 w-3.5" />}
                {t.id === "sales" && <MessageCircle className="h-3.5 w-3.5" />}
                {t.id === "prospect" && <Search className="h-3.5 w-3.5" />}
                {t.id === "voice" && <Mic2 className="h-3.5 w-3.5" />}
                {t.label}
              </button>
            ))}
          </nav>

          <ThemeToggle />
        </header>

        <div className="flex shrink-0 gap-1 overflow-x-auto px-3 pb-2 sm:hidden">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className="rail-btn shrink-0"
              data-tab={t.id}
              data-active={tab === t.id}
              disabled={tabLocked(t.id)}
              onClick={() => selectTab(t.id)}
            >
              {t.label}
            </button>
          ))}
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
                    Add sheets if you need them.
                    <br />
                    <span style={{ color: "var(--coral)" }}>Pick a workflow.</span>
                  </h2>
                </div>

                <ol className="space-y-2">
                  {[
                    { n: "1", ok: connected, t: "Google account", d: email || "Not connected yet" },
                    {
                      n: "2",
                      ok: sheetConfigured,
                      t: "Video list sheet",
                      d: "Only needed for sheet transcription",
                    },
                    {
                      n: "3",
                      ok: outputConfigured,
                      t: "Results sheet",
                      d: "Needed for Run + Voice results",
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

          {tab === "home" && (
            <ModeChooser sheetsReady={sheetsReady} onChoose={chooseWorkflow} />
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

          {tab === "studio" && (
            <StudioWorkspace
              mode={
                workflow === "original" || workflow === "viral" || workflow === "shorts"
                  ? workflow
                  : "original"
              }
              onBack={() => {
                setWorkflow(null);
                selectTab("home");
              }}
            />
          )}

          {tab === "speak" && (
            <SpeakWorkspace
              onBack={() => {
                setWorkflow(null);
                selectTab("home");
              }}
            />
          )}

          {tab === "sales" && (
            <SalesWorkspace
              onBack={() => {
                setWorkflow(null);
                selectTab("home");
              }}
            />
          )}

          {tab === "prospect" && (
            <ProspectWorkspace
              onBack={() => {
                setWorkflow(null);
                selectTab("home");
              }}
            />
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
