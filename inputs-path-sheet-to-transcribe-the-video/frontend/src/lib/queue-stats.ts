import type { BatchQueueResponse, BatchRow } from "./types";
import type { CyberColor } from "@/lib/cyber-theme";
import { cyberColorForIndex } from "@/lib/cyber-theme";

const DONE_ALIASES = new Set(["done", "complete", "completed", "finished", "success"]);
const FAILED_ALIASES = new Set(["failed", "error", "fail"]);
const PROCESSING_ALIASES = new Set(["processing", "running", "in progress", "in_progress"]);
const PENDING_ALIASES = new Set(["pending", "queued", "queue", ""]);

export function normalizeQueueStatus(status: string): string {
  const s = status.trim().toLowerCase();
  if (DONE_ALIASES.has(s)) return "done";
  if (FAILED_ALIASES.has(s)) return "failed";
  if (PROCESSING_ALIASES.has(s)) return "processing";
  if (PENDING_ALIASES.has(s)) return "pending";
  return s;
}

export function computeQueueStats(queue: BatchQueueResponse) {
  const rows = queue.rows;
  let pending = 0;
  let processing = 0;
  let done = 0;
  let failed = 0;

  for (const row of rows) {
    switch (normalizeQueueStatus(row.status)) {
      case "pending":
        pending += 1;
        break;
      case "processing":
        processing += 1;
        break;
      case "done":
        done += 1;
        break;
      case "failed":
        failed += 1;
        break;
      default:
        pending += 1;
        break;
    }
  }

  return {
    pending,
    processing,
    done,
    failed,
    total: rows.length,
  };
}

/** Border color updates live with status — unique neon per row when idle/done. */
export function rowBorderColor(status: string, index: number): CyberColor {
  const s = normalizeQueueStatus(status);
  if (s === "processing") return "orange";
  if (s === "failed") return "red";
  if (s === "pending") return "gold";
  return cyberColorForIndex(index);
}

export function normalizedRowStatus(row: BatchRow): string {
  return normalizeQueueStatus(row.status);
}
