/** Parse H:MM:SS or M:SS label into seconds. */
export function parseTimeLabel(label: string): number | null {
  const parts = label.trim().split(":").map((p) => Number(p));
  if (parts.some((p) => Number.isNaN(p))) return null;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return null;
}

/** Normalize backend progress (0–1 or accidental 0–100). */
export function normalizeProgress(value: number): number {
  const n = value > 1 ? value / 100 : value;
  return Math.max(0, Math.min(1, n));
}

const SETUP_END = 0.12;
const TRANSCRIBE_SPAN = 0.85;

/**
 * Map backend progress + step label to a 0–100% display value.
 * Setup/model load stays 0–12%; transcription follows video time from 12–97%.
 */
export function transcribeProgressFromStep(step: string, backendProgress: number): number {
  const p = normalizeProgress(backendProgress);
  const lower = step.toLowerCase();

  const timeMatch = step.match(/Transcribing (\d+:\d{2}(?::\d{2})?) \/ (\d+:\d{2}(?::\d{2})?)/);
  if (timeMatch) {
    const current = parseTimeLabel(timeMatch[1]);
    const total = parseTimeLabel(timeMatch[2]);
    if (current != null && total != null && total > 0) {
      const ratio = Math.min(1, current / total);
      return Math.min(0.97, SETUP_END + ratio * TRANSCRIBE_SPAN);
    }
  }

  if (
    lower.includes("preparing") ||
    lower.includes("downloading") ||
    lower.includes("starting") ||
    lower.includes("loading whisper") ||
    lower.includes("whisper ready") ||
    lower.includes("retrying") ||
    lower.includes("transcribing with")
  ) {
    if (lower.includes("openai") || lower.includes("still transcribing")) {
      return Math.min(0.48, Math.max(0.15, p));
    }
    if (lower.includes("loading whisper") && !lower.includes("ready")) {
      return Math.min(0.08, p * 0.5);
    }
    return Math.min(0.05, p * 0.3);
  }

  if (lower.includes("finalizing")) {
    return 0.99;
  }

  return p;
}
