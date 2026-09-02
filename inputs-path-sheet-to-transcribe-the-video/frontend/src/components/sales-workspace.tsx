"use client";

import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { ArrowLeft, Copy, Loader2, Mic, MicOff, Send } from "lucide-react";
import { cn } from "@/lib/utils";

type ChatMessage = { role: "customer" | "assistant"; content: string };

interface SalesWorkspaceProps {
  onBack: () => void;
}

function extractSuggestedReply(markdown: string): string {
  const section = markdown.split(/##\s*Suggested reply\s*/i)[1];
  if (!section) return markdown.trim();
  const next = section.split(/\n##\s+/)[0];
  return next.replace(/^```[\w]*\n?/, "").replace(/\n?```$/, "").trim();
}

export function SalesWorkspace({ onBack }: SalesWorkspaceProps) {
  const [context, setContext] = useState("");
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [copied, setCopied] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

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
        context,
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
  }, [context, history, input]);

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
            context,
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

  const copyReply = async () => {
    const text = extractSuggestedReply(markdown);
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4 animate-fade-in-up">
      <header className="flex items-start gap-3">
        <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--coral)]">06 · Sales reply</p>
          <h2 className="text-xl font-extrabold sm:text-2xl">Handle any message like a pro closer</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Paste a chat or record a voice note from the customer — get a calm, rejection-proof reply ready to send.
          </p>
        </div>
      </header>

      <div className="surface-soft space-y-3 p-4">
        <div>
          <Label htmlFor="sales-context">What you&apos;re selling (optional)</Label>
          <textarea
            id="sales-context"
            className="mt-1.5 min-h-[72px] w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            placeholder="e.g. AI automation for dental clinics — booking + follow-ups"
            value={context}
            onChange={(e) => setContext(e.target.value)}
          />
        </div>

        {history.length > 0 && (
          <div className="max-h-40 space-y-2 overflow-y-auto rounded-lg border border-border/60 bg-background/50 p-3 text-sm">
            {history.map((m, i) => (
              <p key={i} className={cn(m.role === "customer" ? "text-muted-foreground" : "font-medium")}>
                <span className="text-xs uppercase tracking-wide opacity-70">
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
            className="mt-1.5 min-h-[100px] w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
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
              Voice message
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
      </div>

      {markdown && (
        <article className="surface-soft prose prose-sm dark:prose-invert max-w-none p-4">
          <div className="mb-3 flex justify-end">
            <Button size="sm" variant="outline" onClick={copyReply}>
              <Copy className="h-3.5 w-3.5" />
              {copied ? "Copied!" : "Copy suggested reply"}
            </Button>
          </div>
          <div className="whitespace-pre-wrap text-sm leading-relaxed">{markdown}</div>
        </article>
      )}
    </div>
  );
}
