"use client";

import { useState } from "react";
import { initials } from "@/lib/api";

/** Faculty photo from the IITR directory, falling back to initials if it fails to load. */
export function FacultyPhoto({
  name,
  src,
  className = "h-14 w-14 rounded-2xl",
}: {
  name: string;
  src: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className={`${className} brand-gradient flex shrink-0 items-center justify-center font-semibold text-white`}>
        {initials(name)}
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- external IITR photos; no optimisation needed
    <img
      src={src}
      alt={`Prof. ${name}`}
      loading="lazy"
      onError={() => setFailed(true)}
      className={`${className} shrink-0 bg-slate-100 object-cover object-top`}
    />
  );
}

/** Circular match score. */
export function MatchRing({ value, size = 48 }: { value: number; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const color = value >= 75 ? "#7c3aed" : value >= 50 ? "#4f46e5" : "#94a3b8";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} title={`${value}% match with your interests`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef0f7" strokeWidth={5} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeLinecap="round"
          strokeDasharray={`${(c * value) / 100} ${c}`}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-slate-700">
        {value}%
      </span>
    </div>
  );
}

export function UserAvatar({ name, className = "h-9 w-9 text-sm" }: { name: string; className?: string }) {
  return (
    <div className={`${className} brand-gradient flex shrink-0 items-center justify-center rounded-full font-semibold text-white`}>
      {initials(name)}
    </div>
  );
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <h2 className="text-lg font-semibold tracking-tight text-slate-900">{children}</h2>
      {action}
    </div>
  );
}

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** A reason worth showing: hide the topic when it just repeats the student's interest. */
export function reasonTopic(r: { interest: string; topic: string }): string | null {
  return r.topic && r.topic.toLowerCase() !== r.interest.toLowerCase() ? r.topic : null;
}

/** Interests of a professor as compact tags (the scraped field is comma-separated).
 *  Deduplicated case-insensitively: some profiles list a topic twice, and tags are keyed by text. */
export function topicList(interests: string | null, max = 6): string[] {
  const seen = new Set<string>();
  return (interests ?? "")
    .split(/\s*[,;]\s*/)
    .map((t) => t.trim())
    .filter((t) => {
      const k = t.toLowerCase();
      if (t.length <= 2 || seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .slice(0, max);
}
