"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { ChatIcon, CloseIcon, LinkIcon, MailIcon, SearchIcon } from "@/components/icons";
import { FacultyPhoto, MatchRing, plural, reasonTopic, topicList } from "@/components/ui";
import InsightCard from "@/components/InsightCard";
import { api, askUrl, type FacultyCard, type FacultyDetail, type Insight } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

type Sort = "match" | "name" | "projects";

export default function ProfessorsPage() {
  const user = useRequireAuth();
  const [faculty, setFaculty] = useState<FacultyCard[] | null>(null);
  const [query, setQuery] = useState("");
  const [interest, setInterest] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("match");
  const [openId, setOpenId] = useState<number | null>(null);

  const interestsKey = user?.interests.join("|");
  useEffect(() => {
    if (!user) return;
    api<FacultyCard[]>("/api/me/faculty").then(setFaculty);
  }, [user, interestsKey]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (faculty ?? []).filter(
      (f) =>
        (!q || f.name.toLowerCase().includes(q) || (f.interests ?? "").toLowerCase().includes(q)) &&
        (!interest || f.matched.includes(interest)),
    );
    if (sort === "name") return [...list].sort((a, b) => a.name.localeCompare(b.name));
    if (sort === "projects") return [...list].sort((a, b) => b.projects - a.projects);
    return list; // the API returns best match first
  }, [faculty, query, interest, sort]);

  if (!user) return null;

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-[1120px] px-6 pb-16 pt-10">
          <div className="flex items-end justify-between gap-6">
            <div>
              <h1 className="headline text-[40px]">Professors</h1>
              <p className="mt-1 text-sm text-slate-500">
                {faculty ? `${faculty.length} ECE faculty` : "Loading faculty…"}
                {user.interests.length > 0 && " · ranked by how well their research matches your interests"}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 shadow-sm focus-within:border-indigo-300">
                <SearchIcon className="h-4 w-4 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search name or topic…"
                  className="w-64 bg-transparent py-2.5 text-sm outline-none"
                />
              </div>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as Sort)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm shadow-sm outline-none"
              >
                <option value="match">Best match</option>
                <option value="projects">Most projects</option>
                <option value="name">Name A–Z</option>
              </select>
            </div>
          </div>

          {user.interests.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-2">
              <FilterChip active={!interest} onClick={() => setInterest(null)}>
                All
              </FilterChip>
              {user.interests.map((i) => (
                <FilterChip key={i} active={interest === i} onClick={() => setInterest(interest === i ? null : i)}>
                  {i}
                </FilterChip>
              ))}
            </div>
          )}

          <div className="mt-6 grid grid-cols-3 gap-5">
            {faculty === null &&
              Array.from({ length: 6 }, (_, i) => <div key={i} className="card h-64 animate-pulse bg-white/60" />)}
            {shown.map((f) => (
              <button
                key={f.id}
                onClick={() => setOpenId(f.id)}
                className="card card-hover flex flex-col p-5 text-left"
              >
                <div className="flex items-start gap-4">
                  <FacultyPhoto name={f.name} src={f.image_url} className="h-16 w-16 rounded-full" />
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold leading-snug text-slate-900">Prof. {f.name}</div>
                    <div className="text-xs text-slate-500">{f.designation}</div>
                  </div>
                  {user.interests.length > 0 && <MatchRing value={f.match} size={44} />}
                </div>
                <div className="mt-4 flex flex-1 flex-wrap content-start gap-1.5">
                  {topicList(f.interests, 4).map((t) => (
                    <span key={t} className="max-w-full truncate rounded-md bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600">
                      {t}
                    </span>
                  ))}
                </div>
                {f.reasons[0] && (
                  <p className="mt-3 truncate text-xs text-indigo-700">
                    ★ {f.reasons[0].interest}
                    {reasonTopic(f.reasons[0]) && ` ↔ ${reasonTopic(f.reasons[0])}`}
                  </p>
                )}
                <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-400">
                  <span>{plural(f.projects, "sponsored project")}</span>
                  <span className="font-medium text-navy">View profile →</span>
                </div>
              </button>
            ))}
          </div>
          {faculty && shown.length === 0 && <p className="mt-10 text-center text-sm text-slate-500">No professors match that search.</p>}
        </div>
      </div>
      {openId !== null && (
        <ProfessorPanel card={faculty?.find((f) => f.id === openId) ?? null} id={openId} onClose={() => setOpenId(null)} />
      )}
    </AppShell>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
        active ? "bg-[#1d1d1f] text-white" : "bg-black/[0.04] text-[#1d1d1f] hover:bg-black/[0.08]"
      }`}
    >
      {children}
    </button>
  );
}

function ProfessorPanel({ id, card, onClose }: { id: number; card: FacultyCard | null; onClose: () => void }) {
  const [detail, setDetail] = useState<FacultyDetail | null>(null);
  const [insights, setInsights] = useState<Insight[] | null>(null);
  useEffect(() => {
    api<FacultyDetail>(`/api/faculty/${id}`).then(setDetail);
    api<{ insights: Insight[] }>(`/api/insights?faculty_id=${id}`)
      .then((d) => setInsights(d.insights))
      .catch(() => setInsights([]));
  }, [id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const name = detail?.name ?? card?.name ?? "";
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={onClose} />
      <aside className="animate-fade-up relative flex h-full w-full max-w-xl flex-col bg-white shadow-2xl">
        <div className="relative bg-[#f5f5f7] px-7 pb-7 pt-8">
          <button onClick={onClose} className="absolute right-4 top-4 rounded-full bg-black/[0.05] p-1.5 text-[#6e6e73] hover:bg-black/10" aria-label="Close">
            <CloseIcon />
          </button>
          <div className="flex items-center gap-5">
            <FacultyPhoto name={name} src={detail?.image_url ?? card?.image_url ?? null} className="h-24 w-24 rounded-full" />
            <div>
              <h2 className="headline text-[28px]">Prof. {name}</h2>
              <p className="text-[15px] text-[#6e6e73]">{detail?.designation ?? card?.designation}</p>
              {card && card.match > 0 && (
                <span className="mt-2 inline-block text-sm font-medium text-navy">
                  {card.match}% match with your interests
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-7 py-6">
          <div className="flex gap-2">
            <Link
              href={askUrl(`Tell me about Prof. ${name}'s research and current projects`)}
              className="brand-gradient flex flex-1 items-center justify-center gap-2 rounded-full py-2.5 text-sm font-semibold text-white"
            >
              <ChatIcon className="h-4 w-4" /> Ask QueryECE
            </Link>
            <Link
              href={`/outreach?draft=${id}`}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl border border-slate-200 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              <MailIcon className="h-4 w-4" /> Draft email
            </Link>
          </div>

          {card && card.reasons.length > 0 && (
            <section className="rounded-2xl bg-[#f5f5f7] p-5">
              <h3 className="text-[17px] font-semibold text-[#1d1d1f]">Why they match you</h3>
              <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                {card.reasons.map((r) => (
                  <li key={r.interest}>
                    Your <b>{r.interest}</b> interest ↔ their work on <b>{reasonTopic(r) ?? r.interest}</b>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="text-[17px] font-semibold text-[#1d1d1f]">Contact</h3>
            <div className="mt-2 space-y-1.5 text-sm">
              {detail?.email && (
                <a href={`mailto:${detail.email}`} className="flex items-center gap-2 text-slate-700 hover:text-navy">
                  <MailIcon className="h-4 w-4 text-slate-400" /> {detail.email}
                </a>
              )}
              {detail?.phone && <p className="pl-6 text-slate-600">{detail.phone}</p>}
              {[detail?.website, detail?.profile_url].filter(Boolean).map((u) => (
                <a key={u} href={u!} target="_blank" rel="noreferrer" className="flex items-center gap-2 truncate text-slate-700 hover:text-navy">
                  <LinkIcon className="h-4 w-4 shrink-0 text-slate-400" /> <span className="truncate">{u}</span>
                </a>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-[17px] font-semibold text-[#1d1d1f]">Research interests</h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {topicList(detail?.interests ?? card?.interests ?? null, 20).map((t) => (
                <span key={t} className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
                  {t}
                </span>
              ))}
            </div>
          </section>

          <section>
            <div className="flex items-baseline justify-between">
              <h3 className="text-[17px] font-semibold text-[#1d1d1f]">From seniors</h3>
              <Link href="/insights" className="text-sm text-navy hover:underline">
                Share one ›
              </Link>
            </div>
            <p className="text-xs text-[#86868b]">Unofficial tips from students who worked with or approached them.</p>
            <div className="mt-3 space-y-2">
              {insights === null && <p className="text-sm text-[#86868b]">Loading…</p>}
              {insights?.length === 0 && <p className="text-sm text-[#6e6e73]">No tips yet about this professor.</p>}
              {insights?.map((i) => (
                <InsightCard
                  key={i.id}
                  compact
                  insight={i}
                  onChange={(n) => setInsights((prev) => (prev ?? []).map((x) => (x.id === n.id ? n : x)))}
                  onRemove={() => setInsights((prev) => (prev ?? []).filter((x) => x.id !== i.id))}
                />
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-[17px] font-semibold text-[#1d1d1f]">
              Sponsored projects {detail ? `(${detail.projects.length})` : ""}
            </h3>
            {!detail && <p className="mt-2 text-sm text-slate-400">Loading…</p>}
            {detail?.projects.length === 0 && <p className="mt-2 text-sm text-slate-500">None listed on the department site.</p>}
            <ol className="relative mt-3 space-y-4 border-l-2 border-indigo-100 pl-5">
              {detail?.projects.map((p, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-indigo-500" />
                  <div className="text-xs font-semibold text-indigo-600">{p.year}</div>
                  <div className="text-sm font-medium leading-snug text-slate-800">{p.title}</div>
                  <div className="text-xs text-slate-500">{p.agency}</div>
                </li>
              ))}
            </ol>
          </section>

          {detail && detail.startups.length > 0 && (
            <section>
              <h3 className="text-[17px] font-semibold text-[#1d1d1f]">Startups</h3>
              {detail.startups.map((s) => (
                <p key={s.name} className="mt-2 text-sm text-slate-700">
                  {s.name}
                  {s.website && (
                    <a href={s.website} target="_blank" rel="noreferrer" className="ml-2 text-navy hover:underline">
                      website
                    </a>
                  )}
                </p>
              ))}
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}
