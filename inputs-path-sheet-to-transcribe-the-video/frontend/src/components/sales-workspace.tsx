"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ProgressBar } from "@/components/progress-bar";
import { toast } from "@/hooks/use-toast";
import { api, waitForJob } from "@/lib/api";
import { normalizeProgress } from "@/lib/progress";
import type { VoiceInfo } from "@/lib/types";
import {
  ArrowLeft,
  Copy,
  Download,
  Loader2,
  Mic,
  MicOff,
  Send,
  Sparkles,
  Volume2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ChatMessage = { role: "customer" | "assistant"; content: string };

interface SalesWorkspaceProps {
  onBack: () => void;
}

const fieldClass = cn(
  "mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm",
  "placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
);

const selectClass = cn(
  "mt-1.5 flex h-11 w-full rounded-xl border border-border bg-background px-3 text-sm",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
);

function extractSuggestedReply(markdown: string): string {
  const section = markdown.split(/##\s*Suggested reply\s*/i)[1];
  if (!section) return markdown.trim();
  const next = section.split(/\n##\s+/)[0];
  return next.replace(/^```[\w]*\n?/, "").replace(/\n?```$/, "").trim();
}

function downloadUrlFor(filename: string, inline = false) {
  const base = `${API_URL}/api/voice/download/${encodeURIComponent(filename)}`;
  return inline ? `${base}?inline=1` : base;
}

async function saveMp3ToDisk(filename: string) {
  const res = await fetch(downloadUrlFor(filename, false));
  if (!res.ok) {
    throw new Error(res.status === 404 ? "File not found" : `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

export function SalesWorkspace({ onBack }: SalesWorkspaceProps) {
  const [offer, setOffer] = useState("");

  // First message / contact
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [notes, setNotes] = useState("");
  const [channel, setChannel] = useState("whatsapp");
  const [firstLoading, setFirstLoading] = useState(false);
  const [firstMarkdown, setFirstMarkdown] = useState("");
  const [messageText, setMessageText] = useState("");
  const [voiceScript, setVoiceScript] = useState("");
  const [copiedFirst, setCopiedFirst] = useState(false);

  // TTS
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [selectedVoice, setSelectedVoice] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [speakProgress, setSpeakProgress] = useState(0);
  const [speakStep, setSpeakStep] = useState("");
  const [mp3Filename, setMp3Filename] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // Reply coach
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [copied, setCopied] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const refreshVoices = useCallback(async () => {
    try {
      const list = await api.voiceList();
      setVoices(list.voices);
      setSelectedVoice((prev) => prev || list.voices[0]?.id || "");
    } catch {
      /* voices optional until TTS */
    }
  }, []);

  useEffect(() => {
    void refreshVoices();
  }, [refreshVoices]);

  const generateFirst = async () => {
    setFirstLoading(true);
    setFirstMarkdown("");
    setMessageText("");
    setVoiceScript("");
    setMp3Filename(null);
    setPreviewUrl(null);
    try {
      const res = await api.salesFirstMessage({
        contact_name: contactName,
        contact_phone: contactPhone,
        contact_email: contactEmail,
        company,
        role,
        notes,
        offer,
        channel,
      });
      setFirstMarkdown(res.markdown);
      setMessageText(res.message_text || "");
      setVoiceScript(res.voice_script || res.message_text || "");
    } catch (e) {
      toast({
        title: "Could not draft first message",
        description: e instanceof Error ? e.message : "Try again",
        variant: "destructive",
      });
    } finally {
      setFirstLoading(false);
    }
  };

  const makeVoiceMp3 = async () => {
    const text = (voiceScript || messageText).trim();
    if (!text) {
      toast({ title: "Generate a first message first", variant: "destructive" });
      return;
    }
    if (!selectedVoice) {
      toast({
        title: "No voice selected",
        description: "Clone a voice in Speak/Voice first, then come back.",
        variant: "destructive",
      });
      return;
    }
    setSpeaking(true);
    setSpeakProgress(0);
    setSpeakStep("Starting…");
    setMp3Filename(null);
    setPreviewUrl(null);
    try {
      const safeName = (contactName || "outreach").replace(/[^\w\-]+/g, "-").slice(0, 40);
      const { job_id } = await api.voiceSpeakText({
        voice_id: selectedVoice,
        text,
        title: `first-msg-${safeName}`,
      });
      const done = await waitForJob(job_id, (s) => {
        setSpeakProgress(normalizeProgress(s.progress));
        setSpeakStep(s.step || s.status);
      });
      const result = done.result as { filename?: string; files?: string[] } | undefined;
      const filename =
        result?.filename || result?.files?.[0]?.split(/[/\\]/).pop();
      if (!filename) throw new Error("No MP3 returned — check Fish Audio / voice setup.");
      setMp3Filename(filename);
      setPreviewUrl(downloadUrlFor(filename, true));
      toast({ title: "Voice message ready", description: "Download the MP3 and send it on WhatsApp." });
    } catch (e) {
      toast({
        title: "Voice conversion failed",
        description: e instanceof Error ? e.message : "Try again",
        variant: "destructive",
      });
    } finally {
      setSpeaking(false);
    }
  };

  const sendText = useCallback(async () => {
    const message = input.trim();
    if (!message) {
      toast({ title: "Paste the customer's message first", variant: "destructive" });
      return;
    }
    setLoading(true);
    setMarkdown("");
    try {
      const res = await api.salesReply({
        message,
        history: history.map((h) => ({ role: h.role, content: h.content })),
        context: offer,
      });
      setMarkdown(res.markdown);
      setHistory((prev) => [
        ...prev,
        { role: "customer", content: message },
        { role: "assistant", content: extractSuggestedReply(res.markdown) },
      ]);
      setInput("");
    } catch (e) {
      toast({
        title: "Could not generate reply",
        description: e instanceof Error ? e.message : "Try again",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [offer, history, input]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const file = new File([blob], `customer-voice-${Date.now()}.webm`, { type: "audio/webm" });
        setLoading(true);
        setMarkdown("");
        try {
          const res = await api.salesReplyVoice({
            file,
            history: history.map((h) => ({ role: h.role, content: h.content })),
            context: offer,
          });
          setMarkdown(res.markdown);
          const transcript = res.transcript || res.customer_message;
          setHistory((prev) => [
            ...prev,
            { role: "customer", content: transcript },
            { role: "assistant", content: extractSuggestedReply(res.markdown) },
          ]);
        } catch (e) {
          toast({
            title: "Voice reply failed",
            description: e instanceof Error ? e.message : "Try again",
            variant: "destructive",
          });
        } finally {
          setLoading(false);
        }
      };
      recorder.start();
      setRecording(true);
    } catch {
      toast({ title: "Microphone access denied", variant: "destructive" });
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  const copyText = async (text: string, which: "first" | "reply") => {
    await navigator.clipboard.writeText(text);
    if (which === "first") {
      setCopiedFirst(true);
      setTimeout(() => setCopiedFirst(false), 2000);
    } else {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="mx-auto w-[90vw] max-w-[90vw] space-y-5 animate-fade-in-up pb-4">
      <header className="flex items-start gap-3">
        <Button variant="ghost" size="icon" onClick={onBack} className="mt-0.5 shrink-0">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--coral)]">
            06 · Sales reply
          </p>
          <h2 className="text-xl font-extrabold sm:text-2xl lg:text-3xl">
            First outreach + reply coach
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground sm:text-base">
            Draft a personalized first message for someone&apos;s contact, turn it into an MP3 voice note,
            then handle their replies like a calm closer.
          </p>
        </div>
      </header>

      <div className="surface-soft p-4 sm:p-5">
        <Label htmlFor="sales-offer">What you&apos;re selling (shared for both tools)</Label>
        <textarea
          id="sales-offer"
          className={cn(fieldClass, "min-h-[68px]")}
          placeholder="e.g. AI automation for dental clinics — booking + follow-ups"
          value={offer}
          onChange={(e) => setOffer(e.target.value)}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2 xl:gap-5">
        {/* —— First message —— */}
        <section className="surface-soft flex flex-col gap-4 p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--neon-teal)]">
                Step A · First message
              </p>
              <h3 className="text-lg font-extrabold">Reach out to a new contact</h3>
              <p className="mt-0.5 text-xs text-muted-foreground sm:text-sm">
                Fill what you know — we write a text + voice-note script you can send.
              </p>
            </div>
            <span className="hidden rounded-full bg-[color-mix(in_srgb,var(--neon-teal)_18%,transparent)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-[var(--neon-teal)] sm:inline">
              Cold / warm open
            </span>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="contact-name">Name</Label>
              <input
                id="contact-name"
                className={fieldClass}
                placeholder="Ayesha Khan"
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="contact-phone">Phone / WhatsApp</Label>
              <input
                id="contact-phone"
                className={fieldClass}
                placeholder="+92 300…"
                value={contactPhone}
                onChange={(e) => setContactPhone(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="contact-email">Email</Label>
              <input
                id="contact-email"
                className={fieldClass}
                placeholder="them@company.com"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="contact-company">Company</Label>
              <input
                id="contact-company"
                className={fieldClass}
                placeholder="Bright Dental"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="contact-role">Role</Label>
              <input
                id="contact-role"
                className={fieldClass}
                placeholder="Owner / Ops manager"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="contact-channel">Channel</Label>
              <select
                id="contact-channel"
                className={selectClass}
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
              >
                <option value="whatsapp">WhatsApp</option>
                <option value="sms">SMS</option>
                <option value="email">Email</option>
                <option value="linkedin">LinkedIn DM</option>
                <option value="call">Call opener</option>
              </select>
            </div>
          </div>

          <div>
            <Label htmlFor="contact-notes">Why them / what you know</Label>
            <textarea
              id="contact-notes"
              className={cn(fieldClass, "min-h-[88px]")}
              placeholder="Saw their clinic on Maps — still taking bookings by phone, slow reviews…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <Button onClick={generateFirst} disabled={firstLoading} className="w-full sm:w-auto">
            {firstLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Draft first message
          </Button>

          {(messageText || firstMarkdown) && (
            <div className="space-y-3 rounded-xl border border-border/70 bg-background/60 p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                  Ready to send
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => copyText(messageText || extractSuggestedReply(firstMarkdown), "first")}
                >
                  <Copy className="h-3.5 w-3.5" />
                  {copiedFirst ? "Copied!" : "Copy text"}
                </Button>
              </div>

              <div>
                <Label htmlFor="first-text">Text message</Label>
                <textarea
                  id="first-text"
                  className={cn(fieldClass, "min-h-[100px] font-medium")}
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                />
              </div>

              <div>
                <Label htmlFor="voice-script">Voice note script (for MP3)</Label>
                <textarea
                  id="voice-script"
                  className={cn(fieldClass, "min-h-[88px]")}
                  value={voiceScript}
                  onChange={(e) => setVoiceScript(e.target.value)}
                />
              </div>

              <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                <div>
                  <Label htmlFor="sales-voice">Voice for MP3</Label>
                  <select
                    id="sales-voice"
                    className={selectClass}
                    value={selectedVoice}
                    onChange={(e) => setSelectedVoice(e.target.value)}
                  >
                    {voices.length === 0 && <option value="">No saved voices — clone one in Speak</option>}
                    {voices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </div>
                <Button onClick={makeVoiceMp3} disabled={speaking || !voices.length} className="sm:mb-0.5">
                  {speaking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
                  Make voice MP3
                </Button>
              </div>

              {speaking && (
                <div className="space-y-1.5">
                  <ProgressBar value={speakProgress} />
                  <p className="text-xs text-muted-foreground">{speakStep}</p>
                </div>
              )}

              {mp3Filename && (
                <div className="flex flex-col gap-2 rounded-lg border border-[color-mix(in_srgb,var(--neon-teal)_40%,transparent)] bg-[color-mix(in_srgb,var(--neon-teal)_10%,transparent)] p-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">Voice message ready</p>
                    <p className="truncate text-xs text-muted-foreground">{mp3Filename}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {previewUrl && (
                      <audio controls src={previewUrl} className="h-9 max-w-full" />
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        try {
                          await saveMp3ToDisk(mp3Filename);
                        } catch (e) {
                          toast({
                            title: "Download failed",
                            description: e instanceof Error ? e.message : "Try again",
                            variant: "destructive",
                          });
                        }
                      }}
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download MP3
                    </Button>
                  </div>
                </div>
              )}

              {firstMarkdown && (
                <details className="text-sm text-muted-foreground">
                  <summary className="cursor-pointer font-medium text-foreground">Full coaching notes</summary>
                  <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-background/80 p-3 text-xs leading-relaxed">
                    {firstMarkdown}
                  </pre>
                </details>
              )}
            </div>
          )}
        </section>

        {/* —— Reply coach —— */}
        <section className="surface-soft flex flex-col gap-4 p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--coral)]">
                Step B · Reply coach
              </p>
              <h3 className="text-lg font-extrabold">Handle their reply</h3>
              <p className="mt-0.5 text-xs text-muted-foreground sm:text-sm">
                Paste a chat or record their voice note — get a rejection-proof response.
              </p>
            </div>
          </div>

          {history.length > 0 && (
            <div className="max-h-44 space-y-2 overflow-y-auto rounded-xl border border-border/60 bg-background/50 p-3 text-sm">
              {history.map((m, i) => (
                <p
                  key={i}
                  className={cn(m.role === "customer" ? "text-muted-foreground" : "font-medium")}
                >
                  <span className="text-[10px] uppercase tracking-wide opacity-70">
                    {m.role === "customer" ? "Customer" : "Your reply"}:
                  </span>{" "}
                  {m.content}
                </p>
              ))}
            </div>
          )}

          <div>
            <Label htmlFor="sales-input">Customer message</Label>
            <textarea
              id="sales-input"
              className={cn(fieldClass, "min-h-[120px]")}
              placeholder="Paste their WhatsApp, email, or DM… e.g. 'Too expensive, maybe next month'"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading || recording}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={sendText} disabled={loading || recording}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Get reply
            </Button>
            {!recording ? (
              <Button type="button" variant="outline" onClick={startRecording} disabled={loading}>
                <Mic className="h-4 w-4" />
                Their voice message
              </Button>
            ) : (
              <Button type="button" variant="destructive" onClick={stopRecording}>
                <MicOff className="h-4 w-4" />
                Stop & analyze
              </Button>
            )}
            {history.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setHistory([]);
                  setMarkdown("");
                }}
              >
                Clear thread
              </Button>
            )}
          </div>

          {markdown && (
            <article className="rounded-xl border border-border/70 bg-background/60 p-3 sm:p-4">
              <div className="mb-3 flex justify-end">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => copyText(extractSuggestedReply(markdown), "reply")}
                >
                  <Copy className="h-3.5 w-3.5" />
                  {copied ? "Copied!" : "Copy suggested reply"}
                </Button>
              </div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed">{markdown}</div>
            </article>
          )}
        </section>
      </div>
    </div>
  );
}
