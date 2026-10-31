"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import InterestInput from "@/components/InterestInput";
import { API_BASE, api, getToken, initials, type User } from "@/lib/api";
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
    "w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-500/10";

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto grid max-w-[1120px] grid-cols-1 gap-6 px-4 pb-16 pt-6 md:px-6 md:pt-10 lg:grid-cols-[340px_1fr]">
          {/* Identity card */}
          <div className="space-y-6">
            <section className="card overflow-hidden text-center">
              <div className="relative h-24 bg-gradient-to-b from-[#e8f2fd] to-white">
                <div className="animate-blob absolute -right-6 -top-10 h-32 w-32 rounded-full bg-white/20 blur-2xl" />
              </div>
              <div className="relative -mt-11 px-6 pb-6">
                <div className="mx-auto flex h-22 w-22 items-center justify-center rounded-full bg-gradient-to-b from-[#b4b4ba] to-[#8e8e93] text-3xl font-medium text-white ring-4 ring-white">
                  {initials(form.name || user.name)}
                </div>
                <h1 className="mt-4 text-xl font-bold text-slate-900">{user.name}</h1>
                <p className="text-sm text-slate-500">
                  {[user.program, user.year].filter(Boolean).join(" · ") || "Add your programme below"}
                </p>
                <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
                  ✓ {user.email}
                </p>
              </div>
            </section>

            <section className="card p-6">
              <h2 className="mb-1 font-semibold text-slate-900">Research interests</h2>
              <p className="mb-4 text-xs text-slate-500">These drive your professor matches, answers and openings.</p>
              <InterestInput value={interests} onChange={setInterests} />
            </section>
          </div>

          <div className="space-y-6">
            <CvCard user={user} onChange={setUser} />
            <AlertsCard user={user} onChange={setUser} />
            <section className="card p-6">
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
                  className="brand-gradient rounded-full px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50 disabled:shadow-none"
                >
                  {saving ? "Saving…" : "Save changes"}
                </button>
              </div>
            </section>

            <section className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
              {[
                [user.stats.chats, "Conversations"],
                [user.stats.questions, "Questions asked"],
                [status?.faculty ?? "–", "Faculty indexed"],
                [status?.opportunities ?? "–", "Open adverts"],
              ].map(([value, label]) => (
                <div key={label as string} className="card p-5 text-center">
                  <div className="headline text-[34px]">{value}</div>
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
    </AppShell>
  );
}

function CvCard({ user, onChange }: { user: User; onChange: (u: User) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const upload = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      // Raw PDF body; the backend extracts and keeps only the text.
      const res = await fetch(`${API_BASE}/api/me/cv`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${getToken()}`,
          "Content-Type": "application/pdf",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
      });
      const body = await res.json();
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Upload failed");
      onChange(body as User);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      onChange(await api<User>("/api/me/cv", { method: "DELETE" }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card flex flex-wrap items-center gap-4 p-5 md:flex-nowrap md:gap-5 md:p-6">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-navy-soft text-sm font-semibold text-navy">
        CV
      </div>
      <div className="min-w-0 flex-1">
        <h2 className="font-semibold text-slate-900">Your CV</h2>
        {user.cv_filename ? (
          <p className="truncate text-sm text-slate-500">
            <span className="font-medium text-emerald-700">✓ {user.cv_filename}</span> · used to personalise answers and
            email drafts
          </p>
        ) : (
          <p className="text-sm text-slate-500">
            Upload a PDF so answers and email drafts can mention your real projects and skills.
          </p>
        )}
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </div>
      <label
        className={`cursor-pointer rounded-xl px-4 py-2.5 text-sm font-semibold ${
          user.cv_filename ? "border border-slate-200 text-slate-700 hover:bg-slate-50" : "brand-gradient text-white"
        } ${busy ? "pointer-events-none opacity-60" : ""}`}
      >
        {busy ? "Working…" : user.cv_filename ? "Replace" : "Upload PDF"}
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = "";
          }}
        />
      </label>
      {user.cv_filename && (
        <button onClick={remove} disabled={busy} className="text-sm text-slate-400 hover:text-red-600">
          Remove
        </button>
      )}
    </section>
  );
}

function AlertsCard({ user, onChange }: { user: User; onChange: (u: User) => void }) {
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    setBusy(true);
    try {
      onChange(await api<User>("/api/me", { method: "PUT", body: JSON.stringify({ email_alerts: !user.email_alerts }) }));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card flex items-center gap-5 p-6">
      <div className="min-w-0 flex-1">
        <h2 className="font-semibold text-[#1d1d1f]">Email alerts</h2>
        <p className="text-sm text-[#6e6e73]">
          A daily email when new openings, projects or notices match your interests, plus follow-up reminders.
        </p>
      </div>
      <button
        role="switch"
        aria-checked={user.email_alerts}
        aria-label="Email alerts"
        disabled={busy}
        onClick={toggle}
        className={`relative h-[31px] w-[51px] shrink-0 rounded-full transition ${user.email_alerts ? "bg-[#34c759]" : "bg-[#e5e5ea]"}`}
      >
        <span
          className={`absolute top-[2px] h-[27px] w-[27px] rounded-full bg-white shadow transition-all ${
            user.email_alerts ? "left-[22px]" : "left-[2px]"
          }`}
        />
      </button>
    </section>
  );
}
