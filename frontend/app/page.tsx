"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AppShell, { OpeningCard } from "@/components/AppShell";
import { ArrowRightIcon, ChatIcon, ClockIcon, FlaskIcon, MailIcon, SendIcon, SparkIcon, UsersIcon } from "@/components/icons";
import { FacultyPhoto, MatchRing, SectionTitle, plural, reasonTopic } from "@/components/ui";
import UpdateList from "@/components/UpdateList";
import { api, askUrl, type HomeData, type UpdateItem } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function HomePage() {
  const user = useRequireAuth();
  const router = useRouter();
  const [data, setData] = useState<HomeData | null>(null);
  const [updates, setUpdates] = useState<UpdateItem[] | null>(null);
  const [question, setQuestion] = useState("");

  const interestsKey = user?.interests.join("|");
  useEffect(() => {
    if (!user) return;
    api<HomeData>("/api/home").then(setData);
    api<UpdateItem[]>("/api/updates?days=30").then(setUpdates).catch(() => setUpdates([]));
  }, [user, interestsKey]);

  if (!user) return null;
  const first = user.name.split(" ")[0];
  const ask = (q: string) => q.trim() && router.push(askUrl(q.trim()));
  const sent = (data?.outreach.by_status.sent ?? 0) + (data?.outreach.by_status.replied ?? 0) +
    (data?.outreach.by_status.meeting ?? 0) + (data?.outreach.by_status.accepted ?? 0);

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-[1120px] px-4 pb-16 pt-2 md:px-6 md:pt-4">
          {/* Hero */}
          <section className="animate-fade-up px-4 pb-4 pt-10 text-center">
            <p className="text-[17px] font-medium text-[#6e6e73]">
              {greeting()}, {first}.
            </p>
            <h1 className="headline mx-auto mt-2 max-w-3xl text-[34px] leading-[1.08] md:text-[52px] md:leading-[1.06]">
              Explore ECE. <span className="brand-text">Ask anything.</span>
            </h1>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                ask(question);
              }}
              className="mx-auto mt-9 flex max-w-2xl items-center gap-2 rounded-full border border-black/[0.08] bg-white py-2 pl-6 pr-2 shadow-[0_8px_30px_-12px_rgba(0,0,0,0.12)] focus-within:border-indigo-300"
            >
              <SparkIcon className="h-5 w-5 text-[#86868b]" />
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Professors, labs, projects, admissions, openings…"
                className="min-w-0 flex-1 bg-transparent px-2 py-2 text-[17px] text-[#1d1d1f] outline-none placeholder:text-[#86868b]"
              />
              <button
                type="submit"
                disabled={!question.trim()}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-navy text-white transition hover:bg-navy-dark disabled:bg-[#e5e5ea] disabled:text-[#86868b]"
                aria-label="Ask"
              >
                <SendIcon className="h-4 w-4" />
              </button>
            </form>
            <div className="mx-auto mt-5 flex max-w-3xl flex-wrap justify-center gap-2">
              {(data?.questions ?? []).slice(0, 4).map((q) => (
                <button
                  key={q}
                  onClick={() => ask(q)}
                  className="rounded-full bg-black/[0.04] px-4 py-2 text-[13px] text-[#1d1d1f] transition hover:bg-black/[0.08]"
                >
                  {q}
                </button>
              ))}
            </div>
          </section>

          {/* Stats */}
          <section className="mt-8 grid grid-cols-2 gap-3 md:mt-10 md:grid-cols-4 md:gap-4">
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

          <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_340px]">
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
                  <Link href="/profile" className="brand-gradient shrink-0 rounded-full px-4 py-2 text-sm font-semibold text-white">
                    Add interests
                  </Link>
                </div>
              ) : data === null ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i} className="card h-48 animate-pulse bg-white/60" />
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {data.matches.map((f, i) => (
                    <div key={f.id} className="card card-hover animate-fade-up flex flex-col p-5" style={{ animationDelay: `${i * 50}ms` }}>
                      <div className="flex items-start gap-4">
                        <FacultyPhoto name={f.name} src={f.image_url} className="h-14 w-14 rounded-full" />
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
                <SectionTitle
                  action={
                    <Link href="/updates" className="text-sm text-navy hover:underline">
                      See all ›
                    </Link>
                  }
                >
                  What&apos;s new
                </SectionTitle>
                <div className="card px-5">
                  {updates === null ? (
                    <p className="py-4 text-sm text-[#86868b]">Loading…</p>
                  ) : updates.length === 0 ? (
                    <p className="py-4 text-sm text-[#6e6e73]">Changes on the ECE website show up here after each crawl.</p>
                  ) : (
                    <UpdateList compact items={[...updates].sort((a, b) => Number(b.for_you) - Number(a.for_you)).slice(0, 4)} />
                  )}
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

function Stat({
  value,
  label,
}: {
  icon?: unknown;
  value: number | string;
  label: string;
  tone?: string;
}) {
  return (
    <div className="card p-6">
      <div className="headline text-[30px] leading-none md:text-[40px]">{value}</div>
      <div className="mt-2 text-sm text-[#6e6e73]">{label}</div>
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
