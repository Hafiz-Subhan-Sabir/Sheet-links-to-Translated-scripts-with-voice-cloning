import type { SheetHistoryItem, SheetSessionResponse } from "./types";

const PREFIX = "voltscript.sheets.";

type SheetCache = {
  input_url: string | null;
  output_url: string | null;
  input_history: SheetHistoryItem[];
  output_history: SheetHistoryItem[];
};

function keyFor(email: string) {
  return `${PREFIX}${email.trim().toLowerCase()}`;
}

export function readSheetCache(email: string): SheetCache {
  const empty: SheetCache = {
    input_url: null,
    output_url: null,
    input_history: [],
    output_history: [],
  };
  if (!email || typeof window === "undefined") return empty;
  try {
    const raw = window.localStorage.getItem(keyFor(email));
    if (!raw) return empty;
    const parsed = JSON.parse(raw) as Partial<SheetCache>;
    return {
      input_url: parsed.input_url || null,
      output_url: parsed.output_url || null,
      input_history: parsed.input_history || [],
      output_history: parsed.output_history || [],
    };
  } catch {
    return empty;
  }
}

export function writeSheetCache(email: string, session: Partial<SheetSessionResponse>) {
  if (!email || typeof window === "undefined") return;
  const next: SheetCache = {
    input_url: session.input_url || null,
    output_url: session.output_url || null,
    input_history: session.input_history || [],
    output_history: session.output_history || [],
  };
  window.localStorage.setItem(keyFor(email), JSON.stringify(next));
}

export function mergeSheetHistory(
  remote: SheetHistoryItem[] = [],
  local: SheetHistoryItem[] = []
): SheetHistoryItem[] {
  const seen = new Set<string>();
  const merged: SheetHistoryItem[] = [];
  for (const item of [...remote, ...local]) {
    const url = (item.url || "").trim();
    if (!url || seen.has(url)) continue;
    seen.add(url);
    merged.push({ ...item, url });
  }
  return merged.slice(0, 8);
}
