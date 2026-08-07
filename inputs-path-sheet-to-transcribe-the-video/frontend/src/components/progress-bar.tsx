"use client";

import { cn } from "@/lib/utils";

interface ProgressBarProps {
  value: number;
  stepLabel?: string;
  className?: string;
  indeterminate?: boolean;
}

export function ProgressBar({
  value,
  stepLabel,
  className,
  indeterminate = false,
}: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-3 text-sm">
        <p className="min-w-0 truncate font-medium text-foreground">
          {stepLabel || (indeterminate ? "Working…" : "Progress")}
        </p>
        <span className="shrink-0 font-mono text-sm tabular-nums text-muted-foreground">
          {indeterminate ? "…" : `${pct}%`}
        </span>
      </div>
      <div
        className="relative h-2.5 overflow-hidden rounded-full"
        style={{ background: "var(--track)" }}
      >
        {indeterminate ? (
          <div
            className="absolute inset-y-0 left-0 w-1/3 rounded-full"
            style={{
              background: "var(--accent)",
              animation: "slide-indeterminate 1.6s ease-in-out infinite",
            }}
          />
        ) : (
          <div
            className="relative h-full rounded-full transition-[width] duration-500 ease-out"
            style={{ width: `${pct}%`, background: "var(--accent)" }}
          >
            <div className="absolute inset-0 overflow-hidden rounded-full">
              <div className="animate-shimmer absolute inset-0 w-full bg-gradient-to-r from-transparent via-white/30 to-transparent" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
