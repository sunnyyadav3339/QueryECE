"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import InsightCard from "@/components/InsightCard";
import { api, type FacultyLite, type Insight } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

const inputCls =
  "w-full rounded-xl border border-[#d2d2d7] bg-white px-4 py-2.5 text-[15px] outline-none transition focus:border-navy focus:ring-4 focus:ring-navy/15";

function linkedId(): number | null {
  if (typeof window === "undefined") return null;
  const v = new URLSearchParams(window.location.search).get("id");
  return v ? Number(v) : null;
}

export default function InsightsPage() {
  const user = useRequireAuth();
  const [items, setItems] = useState<Insight[] | null>(null);
  const [categories, setCategories] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<string | null>(null);
  const [faculty, setFaculty] = useState<FacultyLite[]>([]);
  const [composing, setComposing] = useState(false);
  const [highlight] = useState<number | null>(linkedId);

  useEffect(() => {
    if (!user) return;
    api<{ insights: Insight[]; categories: Record<string, string> }>("/api/insights").then((d) => {
      setItems(d.insights);
      setCategories(d.categories);
    });
    api<FacultyLite[]>("/api/faculty").then(setFaculty).catch(() => {});
  }, [user]);

  useEffect(() => {
    // Opened from a chat citation: scroll to that post.
    if (highlight && items) document.getElementById(`insight-${highlight}`)?.scrollIntoView({ block: "center" });
  }, [highlight, items]);

  if (!user) return null;
  const shown = (items ?? []).filter((i) => !filter || i.category === filter);
  const replace = (next: Insight) => setItems((prev) => (prev ?? []).map((i) => (i.id === next.id ? next : i)));
  const remove = (id: number) => setItems((prev) => (prev ?? []).filter((i) => i.id !== id));

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-[860px] px-6 pb-16 pt-10">
          <h1 className="headline text-[40px] leading-tight">
            Insights from seniors. <span className="brand-text">Not on any website.</span>
          </h1>
          <p className="mt-3 max-w-2xl text-[17px] text-[#6e6e73]">
            What professors look for, how BTP selection works, which electives are worth it, what interviews ask. Share
            what you know; QueryECE uses it, marked as unofficial, when answering juniors.
          </p>

          {composing ? (
            <Composer
              categories={categories}
              faculty={faculty}
              onCancel={() => setComposing(false)}
              onPosted={(i) => {
                setItems((prev) => [i, ...(prev ?? [])]);
                setComposing(false);
              }}
            />
          ) : (
            <button
              onClick={() => setComposing(true)}
              className="mt-7 rounded-full bg-navy px-5 py-2.5 text-[15px] font-medium text-white transition hover:bg-navy-dark"
            >
              Share an insight
            </button>
          )}

          <div className="mt-8 flex flex-wrap gap-2">
            {[[null, "All"] as [string | null, string], ...Object.entries(categories)].map(([key, label]) => (
              <button
                key={label}
                onClick={() => setFilter(key)}
                className={`rounded-full px-4 py-1.5 text-sm transition ${
                  filter === key ? "bg-[#1d1d1f] text-white" : "bg-black/[0.04] text-[#1d1d1f] hover:bg-black/[0.08]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mt-6 space-y-3">
            {items === null && <p className="text-sm text-[#86868b]">Loading…</p>}
            {items && shown.length === 0 && (
              <div className="card p-10 text-center">
                <p className="text-[17px] font-medium text-[#1d1d1f]">Nothing here yet</p>
                <p className="mt-1 text-sm text-[#6e6e73]">Be the first senior to share something useful.</p>
              </div>
            )}
            {shown.map((i) => (
              <InsightCard
                key={i.id}
                insight={i}
                highlight={i.id === highlight}
                onChange={replace}
                onRemove={() => remove(i.id)}
              />
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function Composer({
  categories,
  faculty,
  onCancel,
  onPosted,
}: {
  categories: Record<string, string>;
  faculty: FacultyLite[];
  onCancel: () => void;
  onPosted: (i: Insight) => void;
}) {
  const [category, setCategory] = useState("professor");
  const [facultyId, setFacultyId] = useState<string>("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [anonymous, setAnonymous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const post = async () => {
    setBusy(true);
    setError("");
    try {
      onPosted(
        await api<Insight>("/api/insights", {
          method: "POST",
          body: JSON.stringify({
            category,
            body,
            subject: subject || null,
            faculty_id: facultyId ? Number(facultyId) : null,
            anonymous,
          }),
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't post");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card animate-fade-up mt-7 p-6">
      <div className="grid grid-cols-2 gap-3">
        <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
          {Object.entries(categories).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <select className={inputCls} value={facultyId} onChange={(e) => setFacultyId(e.target.value)}>
          <option value="">No specific professor</option>
          {faculty.map((f) => (
            <option key={f.id} value={f.id}>
              Prof. {f.name}
            </option>
          ))}
        </select>
      </div>
      <input
        className={`${inputCls} mt-3`}
        placeholder="Topic or course (optional), e.g. ECN-311, BTP selection"
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
      />
      <textarea
        className={`${inputCls} mt-3 min-h-32`}
        placeholder="Something a junior would want to know: what worked for you, what to prepare, how they reply…"
        maxLength={800}
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      <div className="mt-1 text-right text-xs text-[#86868b]">{body.length}/800</div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <div className="mt-3 flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm text-[#1d1d1f]">
          <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
          Post anonymously
        </label>
        <div className="flex gap-2">
          <button onClick={onCancel} className="rounded-full px-4 py-2 text-sm text-[#6e6e73] hover:bg-black/[0.04]">
            Cancel
          </button>
          <button
            onClick={post}
            disabled={busy || body.trim().length < 20}
            className="rounded-full bg-navy px-5 py-2 text-sm font-medium text-white transition hover:bg-navy-dark disabled:opacity-40"
          >
            {busy ? "Posting…" : "Post"}
          </button>
        </div>
      </div>
      <p className="mt-3 text-xs text-[#86868b]">
        Be fair and specific. Posts reported by three people are hidden automatically.
      </p>
    </div>
  );
}
