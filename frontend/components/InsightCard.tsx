"use client";

import { useState } from "react";
import { api, type Insight } from "@/lib/api";

const timeAgo = (iso: string | null) => {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days < 1 ? "today" : days < 30 ? `${days}d ago` : new Date(iso).toLocaleDateString(undefined, { month: "short", year: "numeric" });
};

/** One senior's tip, with helpful / report / delete actions. */
export default function InsightCard({
  insight,
  onChange,
  onRemove,
  highlight = false,
  compact = false,
}: {
  insight: Insight;
  onChange: (i: Insight) => void;
  onRemove: () => void;
  highlight?: boolean;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const i = insight;
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <article
      id={`insight-${i.id}`}
      className={`card p-5 transition ${highlight ? "ring-2 ring-navy/40" : ""} ${compact ? "bg-[#f5f5f7]" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[#6e6e73]">
        <span className="font-medium text-[#1d1d1f]">{i.category_label}</span>
        {i.faculty_name && <span>· Prof. {i.faculty_name}</span>}
        {i.subject && <span>· {i.subject}</span>}
      </div>
      <p className="mt-2 whitespace-pre-wrap text-[15px] leading-relaxed text-[#1d1d1f]">{i.body}</p>
      <div className="mt-4 flex items-center justify-between gap-3 text-xs text-[#86868b]">
        <span>
          {i.author}
          {i.author_detail ? ` · ${i.author_detail}` : ""} · {timeAgo(i.created_at)}
        </span>
        <div className="flex items-center gap-3">
          {!i.mine && (
            <button
              disabled={busy}
              onClick={() => act(async () => onChange(await api<Insight>(`/api/insights/${i.id}/helpful`, { method: "POST" })))}
              className={`rounded-full px-3 py-1 font-medium transition ${
                i.voted ? "bg-navy text-white" : "bg-black/[0.04] text-[#1d1d1f] hover:bg-black/[0.08]"
              }`}
            >
              Helpful{i.helpful ? ` · ${i.helpful}` : ""}
            </button>
          )}
          {i.mine && i.helpful > 0 && <span>{i.helpful} found this helpful</span>}
          {!i.mine && !i.reported && (
            <button
              disabled={busy}
              onClick={() =>
                act(async () => {
                  if (!confirm("Report this post as inappropriate or misleading?")) return;
                  const r = await api<{ hidden: boolean }>(`/api/insights/${i.id}/report`, { method: "POST" });
                  if (r.hidden) onRemove();
                  else onChange({ ...i, reported: true });
                })
              }
              className="hover:text-[#1d1d1f]"
            >
              Report
            </button>
          )}
          {i.reported && <span>Reported</span>}
          {i.can_delete && (
            <button
              disabled={busy}
              onClick={() =>
                act(async () => {
                  if (!confirm("Delete this post?")) return;
                  await api(`/api/insights/${i.id}`, { method: "DELETE" });
                  onRemove();
                })
              }
              className="hover:text-red-600"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
