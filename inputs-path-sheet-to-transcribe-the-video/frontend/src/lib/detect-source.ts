const ONLINE_DOMAINS = [
  "youtube.com",
  "youtu.be",
  "vimeo.com",
  "dailymotion.com",
  "twitch.tv",
  "facebook.com",
  "instagram.com",
  "tiktok.com",
  "twitter.com",
  "x.com",
];

const LOCAL_EXTENSIONS = [".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".wav", ".m4a"];

function normalize(value: string): string {
  return value.trim().replace(/^["']|["']$/g, "");
}

function isOnline(value: string): boolean {
  const lower = value.toLowerCase();
  if (lower.startsWith("http://") || lower.startsWith("https://")) return true;
  if (lower.startsWith("www.")) return true;
  return ONLINE_DOMAINS.some((d) => lower.includes(d));
}

function isBareFilename(value: string): boolean {
  if (value.includes("/") || value.includes("\\")) return false;
  if (/^[a-zA-Z]:/.test(value)) return false;
  return LOCAL_EXTENSIONS.some((ext) => value.toLowerCase().endsWith(ext));
}

function isLocal(value: string): boolean {
  const lower = value.toLowerCase();
  if (lower.startsWith("file://")) return true;
  if (/^[a-zA-Z]:\\/.test(value)) return true;
  if (value.startsWith("\\\\")) return true;
  if (value.startsWith("/") && !value.startsWith("//")) return true;
  if (LOCAL_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return !isBareFilename(value);
  }
  return false;
}

export function detectSourceClient(value: string): {
  type: "local" | "online" | null;
  normalized: string;
  valid: boolean;
  message?: string;
} {
  const normalized = normalize(value);
  if (!normalized) {
    return { type: null, normalized: "", valid: false, message: "Please enter a video path or URL" };
  }

  const online = isOnline(normalized);
  const local = isLocal(normalized);

  if (online && local) {
    return {
      type: null,
      normalized,
      valid: false,
      message: "Input is ambiguous — please confirm local file or online URL",
    };
  }

  if (online) {
    let norm = normalized;
    if (norm.startsWith("www.")) norm = `https://${norm}`;
    return { type: "online", normalized: norm, valid: true };
  }

  if (local) {
    let norm = normalized;
    if (norm.toLowerCase().startsWith("file://")) {
      norm = norm.slice(7);
      if (norm.startsWith("/") && /^\/[A-Za-z]:/.test(norm)) norm = norm.slice(1);
    }
    return { type: "local", normalized: norm, valid: true };
  }

  if (isBareFilename(normalized)) {
    return {
      type: null,
      normalized,
      valid: false,
      message: "Use Pick file to upload, or paste the full path (e.g. C:\\Videos\\clip.mp4)",
    };
  }

  return {
    type: null,
    normalized,
    valid: false,
    message: "Could not detect source type — use a valid path or URL",
  };
}
