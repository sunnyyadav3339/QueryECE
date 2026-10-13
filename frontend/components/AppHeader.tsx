"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, initials, type Opportunity } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AppHeader() {
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

  const eceCount = opps?.filter((o) => o.is_ece).length ?? 0;
  const tab = (href: string, label: string) => (
    <Link
      href={href}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
        pathname === href ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:text-slate-800"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <>
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6">
        <div className="flex items-center gap-4 sm:gap-6">
          <Link href="/" className="text-xl font-bold tracking-tight text-navy">
            QueryECE
          </Link>
          <nav className="flex gap-1">
            {tab("/", "Agent")}
            {tab("/outreach", "Outreach")}
            {tab("/profile", "Profile")}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => setDrawerOpen(true)}
            className="relative rounded-full p-2 text-slate-500 hover:bg-slate-100"
            aria-label="Department opportunities"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            {eceCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                {eceCount}
              </span>
            )}
          </button>
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-navy text-sm font-semibold text-white"
            >
              {user ? initials(user.name) : ""}
            </button>
            {menuOpen && user && (
              <div className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
                <div className="px-3 py-2">
                  <div className="text-sm font-semibold text-slate-800">{user.name}</div>
                  <div className="truncate text-xs text-slate-500">{user.email}</div>
                </div>
                <button
                  onClick={() => {
                    logout();
                    router.replace("/login");
                  }}
                  className="w-full rounded-lg px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 flex justify-end">
          <div className="absolute inset-0 bg-slate-900/20 backdrop-blur-sm" onClick={() => setDrawerOpen(false)} />
          <aside className="relative flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Department Opportunities</h2>
                <p className="text-sm text-slate-500">
                  {user?.interests.length ? "Ranked by your research interests" : "Add interests in your profile to rank these"}
                </p>
              </div>
              <button onClick={() => setDrawerOpen(false)} className="p-1 text-slate-400 hover:text-slate-700" aria-label="Close">
                ✕
              </button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
              {opps === null && <p className="text-sm text-slate-400">Loading…</p>}
              {opps && eceCount === 0 && (
                <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-500">
                  No open ECE adverts right now. Showing other current IIT Roorkee openings.
                </p>
              )}
              {opps?.slice(0, 30).map((o) => (
                <div key={o.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                        o.kind.startsWith("Post") ? "bg-violet-50 text-violet-700" : "bg-emerald-50 text-emerald-700"
                      }`}
                    >
                      {o.kind}
                      {o.department ? ` · ${o.department}` : ""}
                    </span>
                    {o.match !== null && o.matched_interest && (
                      <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                        {o.match}% · {o.matched_interest}
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-medium leading-snug text-slate-800">{o.title}</p>
                  {o.deadline && <p className="mt-1 text-xs text-slate-500">Deadline: {o.deadline}</p>}
                  <a
                    href={o.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 inline-block border-t border-slate-100 pt-3 text-sm font-medium text-navy hover:underline"
                  >
                    View advertisement →
                  </a>
                </div>
              ))}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
