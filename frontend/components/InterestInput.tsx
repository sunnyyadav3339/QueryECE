"use client";

import { useState } from "react";

export const SUGGESTED_INTERESTS = [
  "VLSI Design",
  "RF & Microwave",
  "Signal Processing",
  "Wireless Communication",
  "Machine Learning",
  "Embedded Systems",
  "Semiconductor Devices",
  "Antennas",
  "THz Communication",
  "IoT & Sensors",
  "RISC-V",
  "Biomedical Electronics",
];

export default function InterestInput({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  const add = (topic: string) => {
    const t = topic.trim();
    if (!t || value.some((v) => v.toLowerCase() === t.toLowerCase()) || value.length >= 20) return;
    onChange([...value, t]);
    setDraft("");
  };

  const suggestions = SUGGESTED_INTERESTS.filter((s) => !value.includes(s));

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {value.map((topic) => (
          <span
            key={topic}
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-sm text-slate-700"
          >
            {topic}
            <button
              type="button"
              onClick={() => onChange(value.filter((v) => v !== topic))}
              className="text-slate-400 hover:text-slate-700"
              aria-label={`Remove ${topic}`}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add(draft);
            }
          }}
          placeholder="Add topic…"
          className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy"
        />
        <button
          type="button"
          onClick={() => add(draft)}
          className="rounded-lg bg-navy px-4 py-2 text-sm font-medium text-white hover:bg-navy-dark"
        >
          Add
        </button>
      </div>
      {suggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {suggestions.slice(0, 8).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              className="rounded-full border border-dashed border-slate-300 px-2.5 py-0.5 text-xs text-slate-500 hover:border-navy hover:text-navy"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
