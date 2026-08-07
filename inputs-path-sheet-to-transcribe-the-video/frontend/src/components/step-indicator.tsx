"use client";

import type { PipelineStep } from "@/lib/types";
import { PIPELINE_ORDER, PIPELINE_STEPS } from "@/lib/pipeline-steps";
import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

export function StepIndicator({ current }: { current: PipelineStep }) {
  const currentIdx = PIPELINE_ORDER.indexOf(current);
  const progressPct = PIPELINE_ORDER.length > 1 ? (currentIdx / (PIPELINE_ORDER.length - 1)) * 100 : 0;

  return (
    <div className="glass-panel animate-fade-in-up overflow-hidden rounded-2xl px-4 py-5 sm:px-6">
      <div className="relative">
        <div className="absolute left-0 right-0 top-1/2 hidden h-0.5 -translate-y-1/2 bg-border/40 sm:block" />
        <div
          className="absolute left-0 top-1/2 hidden h-0.5 -translate-y-1/2 bg-gradient-to-r from-cyan-500 via-fuchsia-400 to-amber-400 transition-[width] duration-700 ease-out sm:block"
          style={{ width: `${progressPct}%` }}
        />
        <div className="relative flex flex-wrap items-center justify-between gap-2">
          {PIPELINE_STEPS.map((step, i) => {
            const done = i < currentIdx;
            const active = i === currentIdx;
            return (
              <div
                key={step.id}
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition-colors duration-300 sm:px-4 sm:text-sm",
                  done &&
                    "border-cyan-500/35 bg-gradient-to-r from-cyan-500/15 to-emerald-500/10 text-cyan-700 shadow-glow-sm dark:border-cyan-400/40 dark:from-cyan-500/20 dark:to-emerald-500/15 dark:text-cyan-200",
                  active &&
                    "border-fuchsia-400/40 bg-gradient-to-r from-cyan-500/20 via-fuchsia-500/15 to-amber-500/15 text-foreground shadow-glow dark:ring-1 dark:ring-fuchsia-400/20",
                  !done &&
                    !active &&
                    "border-border/60 bg-surface-muted/50 text-muted-foreground dark:border-slate-600/30"
                )}
              >
                <span
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold transition-colors duration-300",
                    done && "bg-gradient-to-br from-cyan-500 to-emerald-500 text-white",
                    active && "bg-gradient-to-br from-cyan-400 via-fuchsia-500 to-amber-400 text-white",
                    !done && !active && "bg-border/80 text-muted-foreground"
                  )}
                >
                  {done ? <Check className="h-3.5 w-3.5" /> : i + 1}
                </span>
                <span className="hidden sm:inline">{step.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
