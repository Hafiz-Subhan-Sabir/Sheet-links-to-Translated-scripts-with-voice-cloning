import type {
  AdminConfigStatusResponse,
  AuthStatusResponse,
  DetectSourceResponse,
  DocsCreateResponse,
  JobStatusResponse,
  PrefetchStatusResponse,
  TranscribeResponse,
  TranslateResponse,
  UploadResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 30000
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_URL}${path}`, {
      credentials: "include",
      signal: controller.signal,
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
    }

    return res.json();
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      const timedOut =
        timeoutMs >= 60 * 60 * 1000
          ? "Processing is taking longer than expected. Check the backend terminal — the first run downloads the AI model (may take several minutes)."
          : "Backend not responding. Is the server running on port 8000?";
      throw new Error(timedOut);
    }
    if (err instanceof TypeError) {
      throw new Error(
        "Lost connection to the backend. If transcription just started, the AI model may still be downloading — check the backend terminal."
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  detectSource: (value: string) =>
    apiFetch<DetectSourceResponse>("/api/detect-source", {
      method: "POST",
      body: JSON.stringify({ value }),
    }),

  transcribe: (body: {
    source: string;
    type: "local" | "online";
    language?: string;
    upload_id?: string;
    prefetch_cache_id?: string;
  }) =>
    apiFetch<TranscribeResponse>("/api/transcribe", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  transcribeSync: (body: {
    source: string;
    type: "local" | "online";
    language?: string;
    upload_id?: string;
    prefetch_cache_id?: string;
  }) =>
    apiFetch<TranscribeResponse>(
      "/api/transcribe/sync",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
      25 * 60 * 1000
    ),

  jobStatus: (jobId: string, includeResult = true) =>
    apiFetch<JobStatusResponse>(
      `/api/jobs/${jobId}/status?include_result=${includeResult ? "true" : "false"}`,
      {},
      120000
    ),

  jobResult: (jobId: string) =>
    apiFetch<TranscribeResponse>(`/api/jobs/${jobId}/result`, {}, 120000),

  translate: (body: { text: string; target_language: string; source_language?: string }) =>
    apiFetch<TranslateResponse>("/api/translate", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  authStatus: () => apiFetch<AuthStatusResponse>("/api/auth/status"),

  disconnectGoogle: () =>
    apiFetch<{ success: boolean }>("/api/auth/disconnect", { method: "POST" }),

  createDoc: (body: {
    title: string;
    transcript: string;
    date: string;
    time: string;
    source_video: string;
    language: string;
    notes?: string;
    log_to_sheet?: boolean;
  }) =>
    apiFetch<DocsCreateResponse>("/api/docs/create", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  adminUnlock: (password: string) =>
    apiFetch<{ success: boolean; message?: string }>("/api/admin/unlock", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  adminLock: () => apiFetch<{ success: boolean }>("/api/admin/lock", { method: "POST" }),

  adminConfigStatus: () => apiFetch<AdminConfigStatusResponse>("/api/admin/config/status"),

  saveAdminConfig: (body: {
    sheet_url: string;
    output_sheet_url?: string;
    docs_folder_id?: string;
    voice_output_dir?: string;
  }) =>
    apiFetch<{ success: boolean }>("/api/admin/config", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  findLocalFile: (filename: string) =>
    apiFetch<{ filename: string; matches: string[] }>("/api/local/find", {
      method: "POST",
      body: JSON.stringify({ filename }),
    }),

  warmupTranscribe: () =>
    apiFetch<{ status: string }>("/api/transcribe/warmup", { method: "POST" }),

  uploadFile: async (file: File, onProgress?: (progress: number) => void): Promise<UploadResponse> => {
    const init = await apiFetch<{ upload_id: string; chunk_size: number }>("/api/upload/init", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, size: file.size }),
    });

    const chunkSize = init.chunk_size;
    const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize));
    const workers = 6;
    let done = 0;
    let nextIndex = 0;

    const uploadChunk = async (index: number) => {
      const start = index * chunkSize;
      const blob = file.slice(start, Math.min(start + chunkSize, file.size));
      const form = new FormData();
      form.append("file", blob, file.name);
      const res = await fetch(`${API_URL}/api/upload/${init.upload_id}/chunk/${index}`, {
        method: "PUT",
        credentials: "include",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(typeof err.detail === "string" ? err.detail : "Chunk upload failed");
      }
      done += 1;
      onProgress?.(done / totalChunks);
    };

    const worker = async () => {
      while (true) {
        const index = nextIndex;
        nextIndex += 1;
        if (index >= totalChunks) break;
        await uploadChunk(index);
      }
    };

    await Promise.all(Array.from({ length: Math.min(workers, totalChunks) }, () => worker()));

    return apiFetch<UploadResponse>("/api/upload/complete", {
      method: "POST",
      body: JSON.stringify({
        upload_id: init.upload_id,
        filename: file.name,
        total_chunks: totalChunks,
      }),
    });
  },

  googleAuthUrl: () => `${API_URL}/api/auth/google`,

  videoPreview: (url: string) =>
    apiFetch<{ title: string; thumbnail: string; duration: number; uploader: string }>(
      "/api/video/preview",
      { method: "POST", body: JSON.stringify({ url }) },
      60000
    ),

  startPrefetch: (url: string) =>
    apiFetch<PrefetchStatusResponse>(
      "/api/video/prefetch",
      { method: "POST", body: JSON.stringify({ url }) },
      60000
    ),

  prefetchStatus: (cacheId: string) =>
    apiFetch<PrefetchStatusResponse>(`/api/video/prefetch/${cacheId}`, {}, 30000),

  batchConfig: () => apiFetch<import("./types").BatchConfigResponse>("/api/batch/config"),

  sheetsSession: () =>
    apiFetch<import("./types").SheetSessionResponse>("/api/sheets/session"),

  sheetsBootstrap: () =>
    apiFetch<import("./types").SheetSessionResponse>("/api/sheets/bootstrap", {
      method: "POST",
    }),

  sheetsUse: (body: { kind: "input" | "output"; url: string; title?: string }) =>
    apiFetch<import("./types").SheetSessionResponse>("/api/sheets/use", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  sheetsCreate: (kind: "input" | "output") =>
    apiFetch<import("./types").SheetSessionResponse>("/api/sheets/create", {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),

  batchQueue: () => apiFetch<import("./types").BatchQueueResponse>("/api/batch/queue"),

  batchOutput: () => apiFetch<import("./types").OutputQueueResponse>("/api/batch/output"),

  batchRun: () =>
    apiFetch<import("./types").BatchRunResponse>("/api/batch/run", { method: "POST" }, 60000),

  batchReset: () =>
    apiFetch<{ success: boolean; cleared_lock: boolean; sheet_rows_reset: number }>(
      "/api/batch/reset",
      { method: "POST" }
    ),

  markDone: (output_row_indexes: number[]) =>
    apiFetch<{ updated: number }>("/api/batch/mark-done", {
      method: "POST",
      body: JSON.stringify({ output_row_indexes }),
    }),

  voiceList: () => apiFetch<import("./types").VoiceListResponse>("/api/voice/list"),

  voiceClone: async (name: string, sample: File) => {
    const form = new FormData();
    form.append("name", name);
    form.append("sample", sample);
    const res = await fetch(`${API_URL}/api/voice/clone`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
    }
    return res.json() as Promise<{ voice: import("./types").VoiceInfo }>;
  },

  voiceCloneFromUrl: (body: {
    url: string;
    name?: string;
    start_sec?: number;
    duration_sec?: number;
  }) =>
    apiFetch<{ job_id: string }>("/api/voice/clone-from-url", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  voiceSetOutputDir: (path: string) =>
    apiFetch<{ success: boolean; voice_output_dir: string }>("/api/voice/output-dir", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  voiceSynthesize: (body: {
    voice_id: string;
    output_row_indexes: number[];
    language_column?: string;
    output_dir?: string;
  }) =>
    apiFetch<{ job_id: string }>("/api/voice/synthesize", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  voiceSpeakText: (body: { voice_id: string; text: string; title?: string; output_dir?: string }) =>
    apiFetch<{ job_id: string }>("/api/voice/speak-text", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  studioOriginal: (body: {
    topic: string;
    niche?: string;
    audience?: string;
    format_hint?: string;
    length_minutes?: number;
  }) =>
    apiFetch<{ mode: string; topic: string; niche: string; markdown: string }>(
      "/api/studio/original",
      { method: "POST", body: JSON.stringify(body) },
      180000
    ),

  studioViral: (body: { urls: string[]; niche?: string; goal?: string }) =>
    apiFetch<{
      mode: string;
      markdown: string;
      videos: {
        title: string;
        view_count: number;
        url: string;
        channel?: string;
        views_per_day?: number | null;
      }[];
    }>("/api/studio/viral", { method: "POST", body: JSON.stringify(body) }, 300000),

  studioShorts: (body: { urls: string[]; niche?: string; goal?: string }) =>
    apiFetch<{
      mode: string;
      markdown: string;
      videos: {
        title: string;
        view_count: number;
        url: string;
        channel?: string;
        views_per_day?: number | null;
      }[];
    }>("/api/studio/shorts", { method: "POST", body: JSON.stringify(body) }, 300000),

  editAutoPack: (body: {
    script: string;
    title?: string;
    voice_mp3_filename?: string;
    generate_images?: boolean;
    build_video?: boolean;
  }) =>
    apiFetch<{ job_id: string }>(
      "/api/edit/auto-pack",
      { method: "POST", body: JSON.stringify(body) },
      60000
    ),

  salesReply: (body: {
    message: string;
    history?: { role: string; content: string }[];
    context?: string;
  }) =>
    apiFetch<{
      mode: string;
      input_type: string;
      customer_message: string;
      markdown: string;
    }>("/api/sales/reply", { method: "POST", body: JSON.stringify(body) }, 120000),

  salesFirstMessage: (body: {
    contact_name?: string;
    contact_phone?: string;
    contact_email?: string;
    company?: string;
    role?: string;
    notes?: string;
    offer?: string;
    channel?: string;
  }) =>
    apiFetch<{
      mode: string;
      contact_name: string;
      channel: string;
      message_text: string;
      voice_script: string;
      markdown: string;
    }>("/api/sales/first-message", { method: "POST", body: JSON.stringify(body) }, 120000),

  salesReplyVoice: async (body: {
    file: File;
    history?: { role: string; content: string }[];
    context?: string;
  }) => {
    const form = new FormData();
    form.append("voice_note", body.file);
    form.append("history_json", JSON.stringify(body.history ?? []));
    form.append("context", body.context ?? "");
    const res = await fetch(`${API_URL}/api/sales/reply-voice`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
    }
    return res.json() as Promise<{
      mode: string;
      input_type: string;
      customer_message: string;
      transcript?: string;
      markdown: string;
    }>;
  },

  prospectAnalyze: (body: {
    video_url?: string;
    website_url?: string;
    google_maps_url?: string;
    app_url?: string;
    business_description?: string;
    your_offer?: string;
  }) =>
    apiFetch<{
      mode: string;
      sources_used: number;
      fetch_warnings: string[];
      markdown: string;
    }>("/api/prospect/analyze", { method: "POST", body: JSON.stringify(body) }, 180000),
};

export function waitForJob(
  jobId: string,
  onUpdate: (status: JobStatusResponse) => void,
  intervalMs = 2000,
  maxWaitMs = 60 * 60 * 1000
): Promise<JobStatusResponse> {
  const started = Date.now();
  let transientErrors = 0;

  return (async () => {
    while (true) {
      if (Date.now() - started > maxWaitMs) {
        throw new Error("Transcription timed out. Try again or use a shorter video.");
      }

      try {
        const status = await api.jobStatus(jobId, false);
        onUpdate(status);

        if (status.status === "completed") {
          const full = await api.jobStatus(jobId, true);
          if (full.result != null) {
            return full;
          }
          // Transcribe jobs historically used /result; other jobs only expose status.result
          try {
            const legacy = await api.jobResult(jobId);
            return { ...full, result: legacy };
          } catch {
            return full;
          }
        }
        if (status.status === "failed") {
          throw new Error(status.error || "Transcription failed");
        }

        transientErrors = 0;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Status check failed";
        if (msg.toLowerCase().includes("not found") || msg.includes("404")) {
          throw new Error(
            "Lost connection to transcription job. Restart the backend and try again."
          );
        }
        if (
          msg.includes("Backend not responding") ||
          msg.includes("Failed to fetch") ||
          msg.includes("NetworkError")
        ) {
          transientErrors += 1;
          if (transientErrors >= 5) {
            throw new Error(
              "Lost connection to the backend while transcribing. Make sure the server is running on port 8000."
            );
          }
          await new Promise((r) => setTimeout(r, intervalMs));
          continue;
        }
        throw err instanceof Error ? err : new Error(msg);
      }

      await new Promise((r) => setTimeout(r, intervalMs));
    }
  })();
}

/** @deprecated use waitForJob */
export function pollJob(
  jobId: string,
  onUpdate: (status: JobStatusResponse) => void,
  intervalMs = 1500
): () => void {
  let active = true;
  const poll = async () => {
    while (active) {
      try {
        const status = await api.jobStatus(jobId);
        onUpdate(status);
        if (status.status === "completed" || status.status === "failed") break;
      } catch {
        break;
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  };
  poll();
  return () => {
    active = false;
  };
}
