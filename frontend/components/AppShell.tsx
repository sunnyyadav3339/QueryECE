"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BriefcaseIcon, ChatIcon, CloseIcon, HomeIcon, LogoutIcon, MailIcon, UserIcon, UsersIcon } from "@/components/icons";
import { UserAvatar } from "@/components/ui";
import { api, type Opportunity } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/chat", label: "Ask QueryECE", icon: ChatIcon },
  { href: "/professors", label: "Professors", icon: UsersIcon },
  { href: "/outreach", label: "Outreach", icon: MailIcon },
  { href: "/profile", label: "Profile", icon: UserIcon },
];

export function Logo({ dark = true }: { dark?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="brand-gradient flex h-9 w-9 items-center justify-center rounded-xl text-lg font-black text-white shadow-lg shadow-indigo-500/30">
        Q
      </div>
      <div className="leading-tight">
        <div className={`text-[17px] font-bold tracking-tight ${dark ? "text-white" : "text-slate-900"}`}>QueryECE</div>
        <div className={`text-[11px] ${dark ? "text-indigo-200/70" : "text-slate-500"}`}>ECE · IIT Roorkee</div>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [opps, setOpps] = useState<Opportunity[] | null>(null);

  const interestsKey = user?.interests.join("|") ?? "";
  useEffect(() => {
    if (!user) return;
    api<Opportunity[]>("/api/opportunities")
      .then(setOpps)
      .catch(() => setOpps([]));
  }, [user, interestsKey]);

  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const eceCount = opps?.filter((o) => o.is_ece).length ?? 0;

  return (
    <div className="flex h-full">
      <aside className="relative flex w-64 shrink-0 flex-col overflow-hidden bg-ink text-slate-300">
        {/* soft glow */}
        <div className="pointer-events-none absolute -left-20 -top-24 h-64 w-64 rounded-full bg-indigo-600/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -right-16 h-56 w-56 rounded-full bg-fuchsia-600/20 blur-3xl" />

        <div className="relative px-5 pb-6 pt-6">
          <Link href="/">
            <Logo />
          </Link>
        </div>

        <nav className="relative flex-1 space-y-1 px-3">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium transition ${
                active(href) ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
              }`}
            >
              <Icon className={`h-5 w-5 ${active(href) ? "text-indigo-300" : "text-slate-500 group-hover:text-slate-300"}`} />
              {label}
              {active(href) && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-indigo-400" />}
            </Link>
          ))}

          <button
            onClick={() => setDrawerOpen(true)}
            className="group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium text-slate-400 transition hover:bg-white/5 hover:text-slate-100"
          >
            <BriefcaseIcon className="h-5 w-5 text-slate-500 group-hover:text-slate-300" />
            Openings
            <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-slate-300">
              {opps ? (eceCount || opps.length) : "…"}
            </span>
          </button>
        </nav>

        {user && (
          <div className="relative m-3 flex items-center gap-3 rounded-2xl bg-white/5 p-3">
            <UserAvatar name={user.name} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-white">{user.name}</div>
              <div className="truncate text-xs text-slate-400">
                {[user.program, user.year].filter(Boolean).join(" · ") || user.email}
              </div>
            </div>
            <button
              onClick={() => {
                logout();
                router.replace("/login");
              }}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogoutIcon className="h-4 w-4" />
            </button>
          </div>
        )}
      </aside>

      <main className="relative min-w-0 flex-1">{children}</main>

      {drawerOpen && <OpeningsDrawer opps={opps} hasInterests={!!user?.interests.length} onClose={() => setDrawerOpen(false)} />}
    </div>
  );
}

function OpeningsDrawer({
  opps,
  hasInterests,
  onClose,
}: {
  opps: Opportunity[] | null;
  hasInterests: boolean;
  onClose: () => void;
}) {
  const eceCount = opps?.filter((o) => o.is_ece).length ?? 0;
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={onClose} />
      <aside className="animate-fade-up relative flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
        <div className="brand-gradient px-6 pb-6 pt-5 text-white">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-lg font-semibold">Openings</h2>
              <p className="text-sm text-indigo-100">
                {hasInterests ? "Project jobs & fellowships, ranked by your interests" : "Add interests in your profile to rank these"}
              </p>
            </div>
            <button onClick={onClose} className="rounded-lg p-1 text-white/80 hover:bg-white/10" aria-label="Close">
              <CloseIcon />
            </button>
          </div>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto bg-canvas px-5 py-5">
          {opps === null && <p className="text-sm text-slate-400">Loading…</p>}
          {opps && eceCount === 0 && (
            <p className="rounded-xl border border-indigo-100 bg-indigo-50 p-3 text-sm text-indigo-800">
              No ECE adverts are open right now. Showing other current IIT Roorkee openings.
            </p>
          )}
          {opps?.slice(0, 30).map((o) => <OpeningCard key={o.id} o={o} />)}
        </div>
      </aside>
    </div>
  );
}

export function OpeningCard({ o }: { o: Opportunity }) {
  return (
    <a href={o.url} target="_blank" rel="noreferrer" className="card card-hover block p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span
          className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
            o.kind.startsWith("Post") ? "bg-violet-50 text-violet-700" : "bg-emerald-50 text-emerald-700"
          }`}
        >
          {o.kind}
          {o.department ? ` · ${o.department}` : ""}
        </span>
        {o.match !== null && o.matched_interest && (
          <span className="brand-gradient rounded-full px-2 py-0.5 text-[11px] font-semibold text-white">
            {o.match}% · {o.matched_interest}
          </span>
        )}
      </div>
      <p className="line-clamp-3 text-sm font-medium leading-snug text-slate-800">
        {o.title.replace(/^Advertisement dated [^:]+:\s*/i, "")}
      </p>
      {o.deadline && <p className="mt-2 text-xs text-slate-500">Deadline · {o.deadline}</p>}
    </a>
  );
}
