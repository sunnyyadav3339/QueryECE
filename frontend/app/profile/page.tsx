"use client";

import { useEffect, useState } from "react";
import AppHeader from "@/components/AppHeader";
import InterestInput from "@/components/InterestInput";
import { api, initials, type User } from "@/lib/api";
import { useAuth, useRequireAuth } from "@/lib/auth";

interface Status {
  last_success_at: string | null;
  crawl_running: boolean;
  pages: number;
  chunks: number;
  faculty: number;
  projects: number;
  opportunities: number;
}

export default function ProfilePage() {
  const user = useRequireAuth();
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    api<Status>("/api/status").then(setStatus).catch(() => {});
  }, []);

  if (!user) return null;
  // Keyed so the form re-initialises from the server copy if the user changes.
  return <ProfileView key={user.id} user={user} status={status} />;
}

function ProfileView({ user, status }: { user: User; status: Status | null }) {
  const { setUser } = useAuth();
  const [form, setForm] = useState({
    name: user.name,
    program: user.program ?? "",
    year: user.year ?? "",
    bio: user.bio ?? "",
  });
  const [interests, setInterests] = useState<string[]>(user.interests);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const dirty =
    form.name !== user.name ||
    form.program !== (user.program ?? "") ||
    form.year !== (user.year ?? "") ||
    form.bio !== (user.bio ?? "") ||
    interests.join("|") !== user.interests.join("|");

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const updated = await api<User>("/api/me", {
        method: "PUT",
        body: JSON.stringify({ ...form, interests }),
      });
      setUser(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const input =
    "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy focus:ring-2 focus:ring-navy/10";

  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <div className="flex-1 overflow-y-auto bg-white">
        <div className="mx-auto grid max-w-5xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[340px_1fr]">
          {/* Identity card */}
          <div className="space-y-6">
            <section className="rounded-2xl border border-slate-200 p-6 text-center">
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-navy text-2xl font-semibold text-white">
                {initials(form.name || user.name)}
              </div>
              <h1 className="mt-4 text-lg font-semibold text-slate-900">{user.name}</h1>
              <p className="text-sm text-slate-500">
                {[user.program, user.year].filter(Boolean).join(", ") || "Add your programme below"}
              </p>
              <p className="mt-3 text-sm text-slate-500">{user.email}</p>
            </section>

            <section className="rounded-2xl border border-slate-200 p-6">
              <h2 className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-700">Research interests</h2>
              <InterestInput value={interests} onChange={setInterests} />
              <p className="mt-3 text-xs text-slate-400">
                Used to personalise answers and rank openings for you.
              </p>
            </section>
          </div>

          <div className="space-y-6">
            <section className="rounded-2xl border border-slate-200 p-6">
              <h2 className="mb-4 font-semibold text-slate-900">Profile details</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block sm:col-span-2">
                  <span className="mb-1 block text-sm font-medium text-slate-700">Full name</span>
                  <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">Programme</span>
                  <input
                    className={input}
                    placeholder="B.Tech ECE"
                    value={form.program}
                    onChange={(e) => setForm({ ...form, program: e.target.value })}
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">Year / semester</span>
                  <input
                    className={input}
                    placeholder="4th semester"
                    value={form.year}
                    onChange={(e) => setForm({ ...form, year: e.target.value })}
                  />
                </label>
                <label className="block sm:col-span-2">
                  <span className="mb-1 block text-sm font-medium text-slate-700">About you</span>
                  <textarea
                    className={`${input} min-h-24`}
                    placeholder="Skills, courses taken, what kind of project you're looking for…"
                    value={form.bio}
                    onChange={(e) => setForm({ ...form, bio: e.target.value })}
                  />
                  <span className="mt-1 block text-xs text-slate-400">The assistant uses this to tailor suggestions.</span>
                </label>
              </div>
              {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
              <div className="mt-5 flex items-center justify-end gap-3">
                {saved && <span className="text-sm text-emerald-600">Saved</span>}
                <button
                  onClick={save}
                  disabled={!dirty || saving}
                  className="rounded-lg bg-navy px-5 py-2 text-sm font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save changes"}
                </button>
              </div>
            </section>

            <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                [user.stats.chats, "Conversations"],
                [user.stats.questions, "Questions asked"],
                [status?.faculty ?? "–", "Faculty indexed"],
                [status?.opportunities ?? "–", "Open adverts"],
              ].map(([value, label]) => (
                <div key={label as string} className="rounded-2xl border border-slate-200 p-4 text-center">
                  <div className="text-2xl font-bold text-slate-900">{value}</div>
                  <div className="mt-1 text-xs text-slate-500">{label}</div>
                </div>
              ))}
            </section>

            {status && (
              <p className="text-xs text-slate-400">
                Knowledge base: {status.pages} pages · {status.chunks} passages · {status.projects} sponsored projects.{" "}
                {status.crawl_running
                  ? "Refreshing from iitr.ac.in now…"
                  : status.last_success_at
                    ? `Last refreshed ${new Date(status.last_success_at).toLocaleString()}.`
                    : "Not refreshed yet."}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
