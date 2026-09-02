"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { ArrowLeft, Copy, Loader2, Search } from "lucide-react";

interface ProspectWorkspaceProps {
  onBack: () => void;
}

export function ProspectWorkspace({ onBack }: ProspectWorkspaceProps) {
  const [videoUrl, setVideoUrl] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [mapsUrl, setMapsUrl] = useState("");
  const [appUrl, setAppUrl] = useState("");
  const [businessDescription, setBusinessDescription] = useState("");
  const [yourOffer, setYourOffer] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const analyze = async () => {
    const hasInput =
      videoUrl.trim() ||
      websiteUrl.trim() ||
      mapsUrl.trim() ||
      appUrl.trim() ||
      businessDescription.trim();
    if (!hasInput) {
      toast({
        title: "Add at least one link or describe the business",
        variant: "destructive",
      });
      return;
    }
    setLoading(true);
    setMarkdown("");
    try {
      const res = await api.prospectAnalyze({
        video_url: videoUrl.trim(),
        website_url: websiteUrl.trim(),
        google_maps_url: mapsUrl.trim(),
        app_url: appUrl.trim(),
        business_description: businessDescription.trim(),
        your_offer: yourOffer.trim(),
      });
      setMarkdown(res.markdown);
      if (res.fetch_warnings?.length) {
        toast({
          title: "Some links could not be fetched",
          description: res.fetch_warnings[0],
        });
      }
    } catch (e) {
      toast({
        title: "Analysis failed",
        description: e instanceof Error ? e.message : "Try again",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const copyAll = async () => {
    await navigator.clipboard.writeText(markdown);
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
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--neon-cyan)]">07 · Problem finder</p>
          <h2 className="text-xl font-extrabold sm:text-2xl">Find their biggest pain before you pitch</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Drop a video, website, Google Maps link, app URL — or describe the business. Get ranked problems and a problem-first pitch opener.
          </p>
        </div>
      </header>

      <div className="surface-soft space-y-3 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Links (any combination)</p>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="prospect-video">Video URL</Label>
            <input
              id="prospect-video"
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder="YouTube, TikTok, Instagram…"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="prospect-website">Website URL</Label>
            <input
              id="prospect-website"
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder="https://theirbusiness.com"
              value={websiteUrl}
              onChange={(e) => setWebsiteUrl(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="prospect-maps">Google Maps URL</Label>
            <input
              id="prospect-maps"
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder="Maps link to their location"
              value={mapsUrl}
              onChange={(e) => setMapsUrl(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="prospect-app">App store URL</Label>
            <input
              id="prospect-app"
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder="Play Store / App Store link"
              value={appUrl}
              onChange={(e) => setAppUrl(e.target.value)}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="prospect-desc">Or describe the business</Label>
          <textarea
            id="prospect-desc"
            className="mt-1.5 min-h-[88px] w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            placeholder="e.g. Family-run HVAC company in Dallas, 8 techs, still taking calls manually…"
            value={businessDescription}
            onChange={(e) => setBusinessDescription(e.target.value)}
          />
        </div>

        <div>
          <Label htmlFor="prospect-offer">What you sell (optional — tailors the pitch)</Label>
          <textarea
            id="prospect-offer"
            className="mt-1.5 min-h-[64px] w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            placeholder="e.g. AI voice agents + CRM automation for home services"
            value={yourOffer}
            onChange={(e) => setYourOffer(e.target.value)}
          />
        </div>

        <Button onClick={analyze} disabled={loading} className="w-full sm:w-auto">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Find their biggest problems
        </Button>
      </div>

      {markdown && (
        <article className="surface-soft prose prose-sm dark:prose-invert max-w-none p-4">
          <div className="mb-3 flex justify-end">
            <Button size="sm" variant="outline" onClick={copyAll}>
              <Copy className="h-3.5 w-3.5" />
              {copied ? "Copied!" : "Copy report"}
            </Button>
          </div>
          <div className="whitespace-pre-wrap text-sm leading-relaxed">{markdown}</div>
        </article>
      )}
    </div>
  );
}
