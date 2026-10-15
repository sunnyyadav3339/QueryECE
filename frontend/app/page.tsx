"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AppShell, { OpeningCard } from "@/components/AppShell";
import { ArrowRightIcon, ChatIcon, ClockIcon, FlaskIcon, MailIcon, SendIcon, SparkIcon, UsersIcon } from "@/components/icons";
import { FacultyPhoto, MatchRing, SectionTitle, plural, reasonTopic } from "@/components/ui";
import { api, askUrl, type HomeData } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function HomePage() {
  const user = useRequireAuth();
  const router = useRouter();
  const [data, setData] = useState<HomeData | null>(null);
  const [question, setQuestion] = useState("");

  const interestsKey = user?.interests.join("|");
  useEffect(() => {
    if (!user) return;
    api<HomeData>("/api/home").then(setData);
  }, [user, interestsKey]);

  if (!user) return null;
  const first = user.name.split(" ")[0];
  const ask = (q: string) => q.trim() && router.push(askUrl(q.trim()));
  const sent = (data?.outreach.by_status.sent ?? 0) + (data?.outreach.by_status.replied ?? 0) +
    (data?.outreach.by_status.meeting ?? 0) + (data?.outreach.by_status.accepted ?? 0);

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">
          {/* Hero */}
          <section className="brand-gradient relative overflow-hidden rounded-[28px] px-10 py-10 text-white shadow-xl shadow-indigo-500/20">
            <div className="animate-blob pointer-events-none absolute -right-10 -top-16 h-64 w-64 rounded-full bg-white/15 blur-2xl" />
            <div className="animate-blob pointer-events-none absolute -bottom-24 left-1/3 h-56 w-56 rounded-full bg-fuchsia-300/20 blur-2xl [animation-delay:-5s]" />
            <div className="relative max-w-3xl">
              <p className="text-sm font-medium text-indigo-100">
                {greeting()}, {first}
              </p>
              <h1 className="mt-1 text-[34px] font-bold leading-tight tracking-tight">
                What would you like to explore in ECE today?
              </h1>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  ask(question);
                }}
                className="mt-6 flex items-center gap-2 rounded-2xl bg-white p-2 shadow-lg shadow-indigo-900/20"
              >
                <SparkIcon className="ml-3 h-5 w-5 text-indigo-500" />
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about professors, labs, projects, admissions or openings…"
                  className="min-w-0 flex-1 bg-transparent px-2 py-2.5 text-[15px] text-slate-800 outline-none placeholder:text-slate-400"
                />
                <button
                  type="submit"
                  disabled={!question.trim()}
                  className="brand-gradient flex h-11 items-center gap-2 rounded-xl px-5 text-sm font-semibold text-white disabled:opacity-60"
                >
                  Ask <SendIcon className="h-4 w-4" />
                </button>
              </form>
              <div className="mt-4 flex flex-wrap gap-2">
                {(data?.questions ?? []).slice(0, 4).map((q) => (
                  <button
                    key={q}
                    onClick={() => ask(q)}
                    className="rounded-full bg-white/15 px-3.5 py-1.5 text-left text-[13px] text-white backdrop-blur transition hover:bg-white/25"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Stats */}
          <section className="mt-6 grid grid-cols-4 gap-4">
            <Stat icon={UsersIcon} tone="indigo" value={data ? data.matches.length : "–"} label="Professors matched to you" />
            <Stat icon={FlaskIcon} tone="violet" value={user.interests.length} label="Research interests" />
            <Stat icon={MailIcon} tone="sky" value={data ? sent : "–"} label="Outreach emails sent" />
            <Stat
              icon={ClockIcon}
              tone="amber"
              value={data ? data.outreach.follow_up_due.length : "–"}
              label="Follow-ups due"
            />
          </section>

          <div className="mt-8 grid grid-cols-[1fr_340px] gap-8">
            {/* Matches */}
            <section>
              <SectionTitle
                action={
                  <Link href="/professors" className="flex items-center gap-1 text-sm font-medium text-navy hover:underline">
                    All professors <ArrowRightIcon className="h-4 w-4" />
                  </Link>
                }
              >
                Professors matched to your interests
              </SectionTitle>

              {!user.interests.length ? (
                <div className="card flex items-center justify-between gap-6 p-6">
                  <div>
                    <p className="font-semibold text-slate-800">Tell QueryECE what you&apos;re into</p>
                    <p className="mt-1 text-sm text-slate-500">
                      Add research interests and we&apos;ll match you with professors, projects and openings.
                    </p>
                  </div>
                  <Link href="/profile" className="brand-gradient shrink-0 rounded-xl px-4 py-2 text-sm font-semibold text-white">
                    Add interests
                  </Link>
                </div>
              ) : data === null ? (
                <div className="grid grid-cols-2 gap-4">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="card h-48 animate-pulse bg-white/60" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-4">
                  {data.matches.map((f, i) => (
                    <div key={f.id} className="card card-hover animate-fade-up flex flex-col p-5" style={{ animationDelay: `${i * 50}ms` }}>
                      <div className="flex items-start gap-4">
                        <FacultyPhoto name={f.name} src={f.image_url} />
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-semibold text-slate-900">Prof. {f.name}</div>
                          <div className="text-xs text-slate-500">{f.designation}</div>
                          <div className="mt-1 text-xs text-slate-400">{plural(f.projects, "sponsored project")}</div>
                        </div>
                        <MatchRing value={f.match} />
                      </div>
                      <div className="mt-4 flex-1 space-y-1.5">
                        {(f.reasons.length ? f.reasons : f.matched.map((m) => ({ interest: m, topic: "" }))).slice(0, 2).map((r) => (
                          <div key={r.interest + r.topic} className="flex items-center gap-2 text-xs">
                            <span className="shrink-0 whitespace-nowrap rounded-md bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700">{r.interest}</span>
                            {reasonTopic(r) && (
                              <>
                                <span className="text-slate-300">↔</span>
                                <span className="truncate text-slate-600">{reasonTopic(r)}</span>
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                      <div className="mt-4 flex gap-2 border-t border-slate-100 pt-4">
                        <Link
                          href={askUrl(`Tell me about Prof. ${f.name}'s research and current projects`)}
                          className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-slate-50 py-2 text-xs font-semibold text-slate-700 hover:bg-indigo-50 hover:text-indigo-700"
                        >
                          <ChatIcon className="h-4 w-4" /> Ask about
                        </Link>
                        <Link
                          href={`/outreach?draft=${f.id}`}
                          className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-slate-50 py-2 text-xs font-semibold text-slate-700 hover:bg-indigo-50 hover:text-indigo-700"
                        >
                          <MailIcon className="h-4 w-4" /> Draft email
                        </Link>
                      </div>
                    </div>
                  ))}
                  {data.matches.length === 0 && (
                    <p className="text-sm text-slate-500">
                      No strong matches yet. Try adding broader interests on your profile.
                    </p>
                  )}
                </div>
              )}
            </section>

            {/* Side column */}
            <div className="space-y-8">
              <section>
                <SectionTitle>Outreach pipeline</SectionTitle>
                <div className="card p-5">
                  {data && data.outreach.total > 0 ? (
                    <>
                      <Pipeline byStatus={data.outreach.by_status} />
                      {data.outreach.follow_up_due.length > 0 && (
                        <p className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
                          Follow up with {data.outreach.follow_up_due.map((n) => `Prof. ${n}`).join(", ")}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-sm text-slate-500">No emails yet. Draft one from a professor card.</p>
                  )}
                  <Link href="/outreach" className="mt-4 flex items-center gap-1 text-sm font-medium text-navy hover:underline">
                    Open tracker <ArrowRightIcon className="h-4 w-4" />
                  </Link>
                </div>
              </section>

              <section>
                <SectionTitle>Openings for you</SectionTitle>
                <div className="space-y-3">
                  {data?.openings.slice(0, 3).map((o) => <OpeningCard key={o.id} o={o} />)}
                  {data && data.openings.length === 0 && <p className="text-sm text-slate-500">No open adverts right now.</p>}
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

const TONES = {
  indigo: "bg-indigo-50 text-indigo-600",
  violet: "bg-violet-50 text-violet-600",
  sky: "bg-sky-50 text-sky-600",
  amber: "bg-amber-50 text-amber-600",
};

function Stat({
  icon: Icon,
  value,
  label,
  tone,
}: {
  icon: (p: { className?: string }) => React.ReactNode;
  value: number | string;
  label: string;
  tone: keyof typeof TONES;
}) {
  return (
    <div className="card flex items-center gap-4 p-5">
      <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${TONES[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <div className="text-2xl font-bold tracking-tight text-slate-900">{value}</div>
        <div className="text-xs text-slate-500">{label}</div>
      </div>
    </div>
  );
}

const STAGES: [string, string, string][] = [
  ["drafted", "Drafted", "bg-slate-400"],
  ["sent", "Sent", "bg-sky-500"],
  ["replied", "Replied", "bg-amber-500"],
  ["meeting", "Meeting", "bg-violet-500"],
  ["accepted", "Accepted", "bg-emerald-500"],
];

function Pipeline({ byStatus }: { byStatus: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(byStatus));
  return (
    <div className="space-y-2.5">
      {STAGES.map(([key, label, color]) => (
        <div key={key} className="flex items-center gap-3 text-xs">
          <span className="w-16 text-slate-500">{label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className={`h-full rounded-full ${color}`} style={{ width: `${((byStatus[key] ?? 0) / max) * 100}%` }} />
          </div>
          <span className="w-4 text-right font-semibold text-slate-700">{byStatus[key] ?? 0}</span>
        </div>
      ))}
    </div>
  );
}
