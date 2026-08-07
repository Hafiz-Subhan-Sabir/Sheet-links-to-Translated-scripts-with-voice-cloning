import type { PipelineStep } from "@/lib/types";

export const PIPELINE_STEPS: { id: PipelineStep; label: string }[] = [
  { id: "input", label: "Video" },
  { id: "transcript", label: "Transcribe" },
  { id: "translate", label: "Translate" },
  { id: "save", label: "Save" },
  { id: "done", label: "Done" },
];

export const PIPELINE_ORDER: PipelineStep[] = ["input", "transcript", "translate", "save", "done"];
