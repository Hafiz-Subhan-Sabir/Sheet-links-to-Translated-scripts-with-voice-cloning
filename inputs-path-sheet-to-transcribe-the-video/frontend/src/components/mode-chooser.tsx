"use client";

import {
  ArrowRight,
  Clapperboard,
  Film,
  Lightbulb,
  MessageCircle,
  Mic2,
  Search,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type WorkflowId =
  | "transcribe"
  | "original"
  | "viral"
  | "shorts"
  | "speak"
  | "sales"
  | "prospect";

type ModeAccent = "coral" | "volt" | "cyan" | "magenta" | "amber" | "teal" | "lime";

type Mode = {
  id: WorkflowId;
  step: string;
  title: string;
  plain: string;
  youGet: string;
  time: string;
  icon: typeof Clapperboard;
  needsSheets: boolean;
  accent: ModeAccent;
};

const MODES: Mode[] = [
  {
    id: "transcribe",
    step: "01",
    title: "Videos on a sheet",
    plain: "Already have links in Google Sheets? Turn them into transcripts and translations.",
    youGet: "Docs + translated scripts, ready for voice",
    time: "Batch",
    icon: Clapperboard,
    needsSheets: true,
    accent: "coral",
  },
  {
    id: "original",
    step: "02",
    title: "Brand-new idea",
    plain: "Type what the video is about. We write titles, a hook, and a full spoken script.",
    youGet: "Script you can record today",
    time: "~1 min",
    icon: Lightbulb,
    needsSheets: false,
    accent: "volt",
  },
  {
    id: "viral",
    step: "03",
    title: "Copy the winners (ethically)",
    plain: "Paste 5–10 videos in your niche. We find patterns, then invent your own angle.",
    youGet: "Original concept + script",
    time: "~2 min",
    icon: TrendingUp,
    needsSheets: false,
    accent: "cyan",
  },
  {
    id: "shorts",
    step: "04",
    title: "Make a Short",
    plain: "Paste viral Shorts. Get hook, body, ending, and a 30–55 second script.",
    youGet: "Hook → body → CTA blueprint",
    time: "~2 min",
    icon: Film,
    needsSheets: false,
    accent: "magenta",
  },
  {
    id: "speak",
    step: "05",
    title: "Any text → MP3",
    plain: "Paste a script. Pick a saved voice or record a new sample. Download the audio.",
    youGet: "Spoken MP3 in your voice",
    time: "Fast",
    icon: Mic2,
    needsSheets: false,
    accent: "amber",
  },
  {
    id: "sales",
    step: "06",
    title: "Sales reply coach",
    plain: "Paste any customer chat or record their voice message. Get a calm, rejection-proof reply.",
    youGet: "Copy-paste reply + objection handling",
    time: "~30 sec",
    icon: MessageCircle,
    needsSheets: false,
    accent: "teal",
  },
  {
    id: "prospect",
    step: "07",
    title: "Find their biggest problem",
    plain: "Drop a video, website, Maps link, or describe the business. Get ranked pains and a pitch opener.",
    youGet: "Problem-first pitch + discovery questions",
    time: "~1 min",
    icon: Search,
    needsSheets: false,
    accent: "lime",
  },
];

interface ModeChooserProps {
  sheetsReady: boolean;
  onChoose: (id: WorkflowId) => void;
}

export function ModeChooser({ sheetsReady, onChoose }: ModeChooserProps) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 animate-fade-in-up">
      <header className="home-hero">
        <p className="home-kicker">Start here</p>
        <h2 className="home-title">
          Pick what you need
          <span className="home-title-accent"> finished.</span>
        </h2>
        <p className="home-sub">
          Seven clear paths. Tap one — we’ll walk you through the rest.
        </p>
      </header>

      <div className="home-path-grid home-path-grid--7">
        {MODES.map((m, i) => {
          const Icon = m.icon;
          const locked = m.needsSheets && !sheetsReady;
          return (
            <button
              key={m.id}
              type="button"
              disabled={locked}
              onClick={() => onChoose(m.id)}
              style={{ animationDelay: `${80 + i * 55}ms` }}
              className={cn(
                "path-card animate-fade-in-up",
                locked && "path-card--locked"
              )}
              data-accent={m.accent}
            >
              <div className="path-card__top">
                <span className="path-card__step">{m.step}</span>
                <span className="path-card__time">{m.time}</span>
              </div>

              <span className="path-card__icon" aria-hidden>
                <Icon className="h-5 w-5" />
              </span>

              <h3 className="path-card__title">{m.title}</h3>
              <p className="path-card__plain">{m.plain}</p>

              <p className="path-card__get">
                <span>You get</span> {m.youGet}
              </p>

              {locked ? (
                <p className="path-card__lock">Link both sheets in Setup first</p>
              ) : (
                <span className="path-card__cta">
                  Let’s go
                  <ArrowRight className="h-4 w-4" />
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
