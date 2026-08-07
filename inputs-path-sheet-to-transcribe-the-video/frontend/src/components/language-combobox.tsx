"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { searchLanguages, type LanguageOption } from "@/lib/languages";
import { ChevronDown, Search } from "lucide-react";

interface LanguageComboboxProps {
  options: LanguageOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  id?: string;
}

export function LanguageCombobox({
  options,
  value,
  onChange,
  placeholder = "Search languages…",
  id,
}: LanguageComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);
  const filtered = useMemo(() => searchLanguages(query, options), [query, options]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  return (
    <div ref={rootRef} className="relative" id={id}>
      <button
        type="button"
        className={cn(
          "flex h-10 w-full items-center justify-between rounded-md border border-zinc-700 bg-zinc-900 px-3 text-sm text-zinc-100",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
        )}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{selected?.label ?? "Select language"}</span>
        <ChevronDown className="h-4 w-4 shrink-0 opacity-60" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-zinc-700 bg-zinc-950 shadow-xl">
          <div className="flex items-center gap-2 border-b border-zinc-800 px-3 py-2">
            <Search className="h-4 w-4 text-zinc-500" />
            <input
              className="w-full bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
              placeholder={placeholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoFocus
            />
          </div>
          <ul className="max-h-56 overflow-y-auto py-1" role="listbox">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-sm text-zinc-500">No languages found</li>
            ) : (
              filtered.map((opt) => (
                <li key={opt.value}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={opt.value === value}
                    className={cn(
                      "flex w-full px-3 py-2 text-left text-sm hover:bg-zinc-800",
                      opt.value === value && "bg-emerald-950/50 text-emerald-300"
                    )}
                    onClick={() => {
                      onChange(opt.value);
                      setOpen(false);
                      setQuery("");
                    }}
                  >
                    <span className="truncate">{opt.label}</span>
                    <span className="ml-auto pl-2 text-xs text-zinc-500">{opt.value}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
          <div className="border-t border-zinc-800 px-3 py-1.5 text-xs text-zinc-500">
            {options.length} languages available
          </div>
        </div>
      )}
    </div>
  );
}
