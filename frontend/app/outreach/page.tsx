"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { api, type FacultyLite, type OutreachCard, type OutreachStatus } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

const STATUS_META: Record<OutreachStatus, { label: string; dot: string }> = {
  drafted: { label: "Drafted", dot: "bg-slate-400" },
  sent: { label: "Sent", dot: "bg-blue-500" },
  replied: { label: "Replied", dot: "bg-amber-500" },
  meeting: { label: "Meeting", dot: "bg-violet-500" },
  accepted: { label: "Accepted", dot: "bg-emerald-500" },
  rejected: { label: "Not now", dot: "bg-rose-400" },
};
const STATUSES = Object.keys(STATUS_META) as OutreachStatus[];
const FOLLOW_UP = "Follow-up on my earlier email";

const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
const fmt = (d: string | null) =>
  d ? new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "";
const isDue = (c: OutreachCard) => c.status === "sent" && !!c.follow_up_on && c.follow_up_on <= today();

const inputCls =
  "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy focus:ring-2 focus:ring-navy/10";

export default function OutreachPage() {
  const user = useRequireAuth();
  const [cards, setCards] = useState<OutreachCard[] | null>(null);
  const [purposes, setPurposes] = useState<string[]>([]);
  const [faculty, setFaculty] = useState<FacultyLite[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  // Deep link from chat: /outreach?draft=<faculty_id>. Nothing renders before auth
  // resolves on the client, so reading window here can't cause a hydration mismatch.
  const [composer, setComposer] = useState<{ facultyId: number | null } | null>(() => {
    const id = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("draft");
    return id ? { facultyId: Number(id) } : null;
  });

  useEffect(() => {
    if (!user) return;
    api<{ cards: OutreachCard[]; purposes: string[] }>("/api/outreach").then((d) => {
      setCards(d.cards);
      setPurposes(d.purposes);
    });
    api<FacultyLite[]>("/api/faculty").then(setFaculty);
    if (window.location.search) window.history.replaceState(null, "", "/outreach");
  }, [user]);

  const upsert = (card: OutreachCard) =>
    setCards((prev) => [card, ...(prev ?? []).filter((c) => c.id !== card.id)]);

  if (!user) return null;
  const open = cards?.find((c) => c.id === openId) ?? null;
  const due = cards?.filter(isDue) ?? [];

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-7xl px-8 py-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">Professor outreach</h1>
              <p className="mt-1 text-sm text-slate-500">
                Draft personalised emails from each professor&apos;s real research, send them from your own inbox, and
                track replies.
              </p>
            </div>
            <button
              onClick={() => setComposer({ facultyId: null })}
              className="brand-gradient rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 hover:opacity-95"
            >
              + Draft new email
            </button>
          </div>

          {due.length > 0 && (
            <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <span className="font-semibold">Follow-up due:</span>{" "}
              {due.map((c, i) => (
                <span key={c.id}>
                  {i > 0 && ", "}
                  <button onClick={() => setOpenId(c.id)} className="underline underline-offset-2">
                    Prof. {c.professor_name}
                  </button>
                </span>
              ))}
              . No reply in a week; a short, polite follow-up is fine.
            </div>
          )}

          {cards === null ? (
            <p className="mt-10 text-sm text-slate-400">Loading…</p>
          ) : cards.length === 0 ? (
            <div className="card mt-10 p-12 text-center">
              <p className="font-medium text-slate-700">No outreach yet</p>
              <p className="mt-1 text-sm text-slate-500">
                Pick a professor and QueryECE will draft an email using their projects and your profile.
              </p>
              <div className="mt-5 flex justify-center gap-3">
                <button
                  onClick={() => setComposer({ facultyId: null })}
                  className="brand-gradient rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-500/20"
                >
                  Draft your first email
                </button>
                <Link href="/professors" className="rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                  Browse professors
                </Link>
              </div>
            </div>
          ) : (
            <div className="mt-6 flex gap-4 overflow-x-auto pb-4">
              {STATUSES.map((s) => {
                const col = cards.filter((c) => c.status === s);
                return (
                  <section key={s} className="min-w-[200px] flex-1 rounded-2xl border border-slate-200/70 bg-white/50 p-3">
                    <h2 className="mb-3 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wider text-slate-600">
                      <span className={`h-2 w-2 rounded-full ${STATUS_META[s].dot}`} />
                      {STATUS_META[s].label}
                      <span className="ml-auto font-normal text-slate-400">{col.length}</span>
                    </h2>
                    <div className="space-y-2">
                      {col.map((c) => (
                        <button
                          key={c.id}
                          onClick={() => setOpenId(c.id)}
                          className="card card-hover block w-full p-3.5 text-left"
                        >
                          <div className="text-sm font-semibold text-slate-800">Prof. {c.professor_name}</div>
                          <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{c.subject || c.purpose}</div>
                          <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                            {c.sent_on && <span className="text-slate-400">Sent {fmt(c.sent_on)}</span>}
                            {c.sent.length > 1 && <span className="text-slate-400">· {c.sent.length} emails</span>}
                            {isDue(c) && (
                              <span className="rounded bg-amber-100 px-1.5 font-medium text-amber-700">Follow up</span>
                            )}
                            {c.status === "sent" && c.follow_up_on && !isDue(c) && (
                              <span className="text-slate-400">· nudge {fmt(c.follow_up_on)}</span>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {composer && (
        <Composer
          faculty={faculty}
          purposes={purposes.filter((p) => p !== FOLLOW_UP)}
          initialFacultyId={composer.facultyId}
          existing={cards ?? []}
          onClose={() => setComposer(null)}
          onDrafted={(card) => {
            upsert(card);
            setComposer(null);
            setOpenId(card.id);
          }}
        />
      )}
      {open && (
        <Editor
          key={open.id}
          card={open}
          purposes={purposes}
          onClose={() => setOpenId(null)}
          onChange={upsert}
          onDelete={() => {
            setCards((prev) => (prev ?? []).filter((c) => c.id !== open.id));
            setOpenId(null);
          }}
        />
      )}
    </AppShell>
  );
}

function Composer({
  faculty,
  purposes,
  initialFacultyId,
  existing,
  onClose,
  onDrafted,
}: {
  faculty: FacultyLite[];
  purposes: string[];
  initialFacultyId: number | null;
  existing: OutreachCard[];
  onClose: () => void;
  onDrafted: (c: OutreachCard) => void;
}) {
  const [query, setQuery] = useState("");
  const [facultyId, setFacultyId] = useState<number | null>(initialFacultyId);
  const [purpose, setPurpose] = useState(purposes[0] ?? "Research internship / project");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return faculty.filter(
      (f) => !q || f.name.toLowerCase().includes(q) || (f.interests ?? "").toLowerCase().includes(q),
    );
  }, [faculty, query]);
  const chosen = faculty.find((f) => f.id === facultyId);
  const already = existing.find((c) => c.faculty_id === facultyId);

  const generate = async () => {
    if (!facultyId) return;
    setBusy(true);
    setError("");
    try {
      onDrafted(
        await api<OutreachCard>("/api/outreach/draft", {
          method: "POST",
          body: JSON.stringify({ faculty_id: facultyId, purpose, note }),
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't generate the draft");
      setBusy(false);
    }
  };

  return (
    <Overlay onClose={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-lg font-semibold text-slate-900">Draft an email</h2>
        <p className="mt-1 text-sm text-slate-500">
          Uses the professor&apos;s research interests and sponsored projects, plus your profile.
        </p>

        <div className="mt-5 space-y-4">
          <div>
            <span className="mb-1 block text-sm font-medium text-slate-700">Professor</span>
            {chosen ? (
              <div className="flex items-start justify-between gap-3 rounded-lg border border-navy/30 bg-blue-50/40 p-3">
                <div>
                  <div className="text-sm font-semibold text-slate-800">Prof. {chosen.name}</div>
                  <div className="line-clamp-2 text-xs text-slate-500">{chosen.interests}</div>
                </div>
                <button onClick={() => setFacultyId(null)} className="text-xs text-navy hover:underline">
                  Change
                </button>
              </div>
            ) : (
              <>
                <input
                  autoFocus
                  className={inputCls}
                  placeholder="Search by name or topic, e.g. VLSI, antenna"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-slate-100">
                  {matches.map((f) => (
                    <button
                      key={f.id}
                      onClick={() => setFacultyId(f.id)}
                      className="block w-full border-b border-slate-50 px-3 py-2 text-left hover:bg-slate-50"
                    >
                      <div className="text-sm font-medium text-slate-800">Prof. {f.name}</div>
                      <div className="truncate text-xs text-slate-500">{f.interests}</div>
                    </button>
                  ))}
                  {matches.length === 0 && <p className="px-3 py-2 text-sm text-slate-400">No match</p>}
                </div>
              </>
            )}
          </div>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">What are you asking for?</span>
            <select className={inputCls} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              {purposes.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">Anything to mention? (optional)</span>
            <textarea
              className={`${inputCls} min-h-20`}
              placeholder="e.g. available May–July, CGPA 8.6, built an FPGA image filter"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>

          {already && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
              You already have a card for this professor. Its working draft will be replaced; emails you marked as
              sent are kept.
            </p>
          )}
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-600 hover:bg-slate-50">
            Cancel
          </button>
          <button
            onClick={generate}
            disabled={!facultyId || busy}
            className="brand-gradient rounded-xl px-5 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Writing…" : "Generate draft"}
          </button>
        </div>
      </div>
    </Overlay>
  );
}

function Editor({
  card,
  purposes,
  onClose,
  onChange,
  onDelete,
}: {
  card: OutreachCard;
  purposes: string[];
  onClose: () => void;
  onChange: (c: OutreachCard) => void;
  onDelete: () => void;
}) {
  const [subject, setSubject] = useState(card.subject);
  const [body, setBody] = useState(card.body);
  const [notes, setNotes] = useState(card.notes);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [purpose, setPurpose] = useState(card.sent.length ? FOLLOW_UP : (card.purpose ?? purposes[0]));
  const dirty = subject !== card.subject || body !== card.body || notes !== card.notes;
  const draftIsSent = card.sent.some((s) => s.body === card.body);

  const patch = async (changes: Record<string, unknown>, label: string) => {
    setBusy(label);
    setError("");
    try {
      const updated = await api<OutreachCard>(`/api/outreach/${card.id}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      onChange(updated);
      return updated;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save");
    } finally {
      setBusy("");
    }
  };
  const edits = () => (dirty ? { subject, body, notes } : {});

  const regenerate = async () => {
    if (dirty && !confirm("Replace your edits with a new draft?")) return;
    setBusy("Writing…");
    setError("");
    try {
      const updated = await api<OutreachCard>("/api/outreach/draft", {
        method: "POST",
        body: JSON.stringify({ faculty_id: card.faculty_id, purpose }),
      });
      onChange(updated);
      setSubject(updated.subject);
      setBody(updated.body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't generate the draft");
    } finally {
      setBusy("");
    }
  };

  const to = card.professor_email ?? "";
  const gmail = `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to)}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  const mailto = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;

  return (
    <Overlay onClose={onClose} side>
      <aside className="flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Prof. {card.professor_name}</h2>
            <p className="text-sm text-slate-500">{to}</p>
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-700" aria-label="Close">
            ✕
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">Status</span>
              <select
                className={inputCls}
                value={card.status}
                onChange={(e) => patch({ ...edits(), status: e.target.value }, "Saving…")}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_META[s].label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">
                Follow up on
              </span>
              <input
                type="date"
                className={inputCls}
                value={card.follow_up_on ?? ""}
                onChange={(e) => patch({ follow_up_on: e.target.value || null }, "Saving…")}
              />
            </label>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                {draftIsSent ? "Email (sent)" : "Draft"}
              </span>
              <div className="flex items-center gap-2">
                <select
                  className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600"
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                >
                  {purposes.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
                <button
                  onClick={regenerate}
                  disabled={!!busy}
                  className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-navy hover:bg-slate-50 disabled:opacity-50"
                >
                  {purpose === FOLLOW_UP ? "Write follow-up" : "Rewrite"}
                </button>
              </div>
            </div>
            <input className={`${inputCls} font-medium`} value={subject} onChange={(e) => setSubject(e.target.value)} />
            <textarea
              className={`${inputCls} mt-2 min-h-80 leading-relaxed`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-400">
              Check every claim before sending; the draft only uses your profile and the department website.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <a
              href={gmail}
              target="_blank"
              rel="noreferrer"
              className="brand-gradient rounded-xl px-4 py-2 text-sm font-semibold text-white"
            >
              Open in Gmail
            </a>
            <a href={mailto} className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
              Mail app
            </a>
            <button
              onClick={async () => {
                await navigator.clipboard.writeText(body);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              {copied ? "Copied" : "Copy text"}
            </button>
            <button
              onClick={() => patch({ ...edits(), status: "sent" }, "Saving…")}
              disabled={!!busy || draftIsSent}
              className="ml-auto rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
              title="Record that you sent this email; sets a follow-up reminder for a week later"
            >
              {draftIsSent ? "Marked as sent" : "Mark as sent"}
            </button>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-500">Notes</span>
            <textarea
              className={`${inputCls} min-h-20`}
              placeholder="Replies, meeting times, what they asked for…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>

          {card.sent.length > 0 && (
            <details className="rounded-xl border border-slate-200 p-4">
              <summary className="cursor-pointer text-sm font-medium text-slate-700">
                Sent emails ({card.sent.length})
              </summary>
              <div className="mt-3 space-y-4">
                {[...card.sent].reverse().map((s, i) => (
                  <div key={i} className="border-t border-slate-100 pt-3 first:border-0 first:pt-0">
                    <div className="text-xs text-slate-400">{fmt(s.sent_on)}</div>
                    <div className="text-sm font-medium text-slate-800">{s.subject}</div>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{s.body}</p>
                  </div>
                ))}
              </div>
            </details>
          )}
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
        </div>

        <div className="flex items-center justify-between border-t border-slate-100 px-6 py-4">
          <button
            onClick={async () => {
              if (!confirm(`Remove Prof. ${card.professor_name} from your tracker?`)) return;
              await api(`/api/outreach/${card.id}`, { method: "DELETE" });
              onDelete();
            }}
            className="text-sm text-slate-400 hover:text-red-600"
          >
            Delete
          </button>
          <div className="flex items-center gap-3">
            {busy && <span className="text-sm text-slate-400">{busy}</span>}
            <button
              onClick={() => patch({ subject, body, notes }, "Saving…")}
              disabled={!dirty || !!busy}
              className="brand-gradient rounded-xl px-5 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>
      </aside>
    </Overlay>
  );
}

function Overlay({ children, onClose, side }: { children: React.ReactNode; onClose: () => void; side?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className={`fixed inset-0 z-40 flex ${side ? "justify-end" : "items-center justify-center p-4"}`}>
      <div className="absolute inset-0 bg-slate-900/20 backdrop-blur-sm" onClick={onClose} />
      {/* The wrapper ignores clicks so the backdrop beside the panel still closes it. */}
      <div
        className={`pointer-events-none relative flex *:pointer-events-auto ${
          side ? "h-full w-full justify-end" : "w-full justify-center"
        }`}
      >
        {children}
      </div>
    </div>
  );
}
