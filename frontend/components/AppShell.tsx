"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CloseIcon } from "@/components/icons";
import { UserAvatar } from "@/components/ui";
import { api, type Opportunity } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/chat", label: "Ask" },
  { href: "/professors", label: "Professors" },
  { href: "/insights", label: "Insights" },
  { href: "/updates", label: "What's new" },
  { href: "/outreach", label: "Outreach" },
  { href: "/profile", label: "Profile" },
];

export function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`flex h-7 w-7 items-center justify-center rounded-[8px] text-[13px] font-semibold ${
          dark ? "bg-white text-[#1d1d1f]" : "bg-[#1d1d1f] text-white"
        }`}
      >
        Q
      </div>
      <span className={`text-[15px] font-semibold tracking-tight ${dark ? "text-white" : "text-[#1d1d1f]"}`}>QueryECE</span>
    </div>
  );
}

/** Frosted top navigation bar (apple.com style) above the page. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [opps, setOpps] = useState<Opportunity[] | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const interestsKey = user?.interests.join("|") ?? "";
  useEffect(() => {
    if (!user) return;
    api<Opportunity[]>("/api/opportunities")
      .then(setOpps)
      .catch(() => setOpps([]));
  }, [user, interestsKey]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const eceCount = opps?.filter((o) => o.is_ece).length ?? 0;

  return (
    <div className="flex h-full flex-col">
      <header className="glass sticky top-0 z-30 border-b border-black/[0.06]">
        <div className="mx-auto flex h-12 max-w-[1120px] items-center justify-between px-6">
          <Link href="/">
            <Logo />
          </Link>
          <nav className="flex items-center gap-1">
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`rounded-full px-3.5 py-1 text-[13px] transition ${
                  active(href) ? "bg-black/[0.06] font-medium text-[#1d1d1f]" : "text-[#1d1d1f]/70 hover:text-[#1d1d1f]"
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setDrawerOpen(true)}
              className="text-[13px] text-[#1d1d1f]/70 transition hover:text-[#1d1d1f]"
            >
              Openings
              {opps && <span className="ml-1.5 text-[#86868b]">{eceCount || opps.length}</span>}
            </button>
            <div className="relative" ref={menuRef}>
              <button onClick={() => setMenuOpen((v) => !v)} aria-label="Account" className="block">
                {user && <UserAvatar name={user.name} className="h-7 w-7 text-[11px]" />}
              </button>
              {menuOpen && user && (
                <div className="animate-fade-up absolute right-0 mt-2 w-60 rounded-2xl border border-black/[0.06] bg-white/95 p-1.5 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.25)] backdrop-blur">
                  <div className="px-3 py-2.5">
                    <div className="text-sm font-medium text-[#1d1d1f]">{user.name}</div>
                    <div className="truncate text-xs text-[#86868b]">{user.email}</div>
                  </div>
                  <Link href="/profile" className="block rounded-xl px-3 py-2 text-sm text-[#1d1d1f] hover:bg-black/[0.04]">
                    Profile
                  </Link>
                  <button
                    onClick={() => {
                      logout();
                      router.replace("/login");
                    }}
                    className="w-full rounded-xl px-3 py-2 text-left text-sm text-[#1d1d1f] hover:bg-black/[0.04]"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="relative min-h-0 flex-1">{children}</main>

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
      <div className="absolute inset-0 bg-black/20 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="animate-fade-up relative flex h-full w-full max-w-md flex-col bg-[#f5f5f7]">
        <div className="flex items-start justify-between px-7 pb-4 pt-7">
          <div>
            <h2 className="headline text-2xl">Openings</h2>
            <p className="mt-1 text-sm text-[#6e6e73]">
              {hasInterests ? "Project jobs and fellowships, ranked for you." : "Add interests in your profile to rank these."}
            </p>
          </div>
          <button onClick={onClose} className="rounded-full bg-black/[0.05] p-1.5 text-[#6e6e73] hover:bg-black/10" aria-label="Close">
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto px-5 pb-6">
          {opps === null && <p className="px-2 text-sm text-[#86868b]">Loading…</p>}
          {opps && eceCount === 0 && (
            <p className="px-2 text-sm text-[#6e6e73]">No ECE adverts are open right now. Showing other IIT Roorkee openings.</p>
          )}
          {opps?.slice(0, 30).map((o) => <OpeningCard key={o.id} o={o} />)}
        </div>
      </aside>
    </div>
  );
}

export function OpeningCard({ o }: { o: Opportunity }) {
  return (
    <a href={o.url} target="_blank" rel="noreferrer" className="card card-hover block p-5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-medium text-[#6e6e73]">
          {o.kind}
          {o.department ? ` · ${o.department}` : ""}
        </span>
        {o.match !== null && o.matched_interest && (
          <span className="font-medium text-navy">
            {o.match}% · {o.matched_interest}
          </span>
        )}
      </div>
      <p className="line-clamp-3 text-[15px] font-medium leading-snug text-[#1d1d1f]">
        {o.title.replace(/^Advertisement dated [^:]+:\s*/i, "")}
      </p>
      {o.deadline && <p className="mt-2 text-xs text-[#86868b]">Deadline · {o.deadline}</p>}
      <span className="mt-3 inline-block text-sm text-navy">View advert ›</span>
    </a>
  );
}
