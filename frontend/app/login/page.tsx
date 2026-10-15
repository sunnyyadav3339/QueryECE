"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/AppShell";
import { BookIcon, ChatIcon, MailIcon, UsersIcon } from "@/components/icons";
import InterestInput from "@/components/InterestInput";
import { api, type AuthResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Mode = "login" | "register";

interface Status {
  pages: number;
  faculty: number;
  projects: number;
  opportunities: number;
}

const FEATURES = [
  { icon: ChatIcon, title: "Ask anything about ECE", text: "Answers with sources from the department website, refreshed weekly." },
  { icon: UsersIcon, title: "Find your professors", text: "Faculty ranked by how well their research matches your interests." },
  { icon: MailIcon, title: "Reach out with confidence", text: "Personalised emails from real projects, plus a tracker for replies." },
];

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [program, setProgram] = useState("");
  const [year, setYear] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [verifyEmail, setVerifyEmail] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  useEffect(() => {
    api<Status>("/api/status").then(setStatus).catch(() => {});
  }, []);

  const finish = (res: AuthResult) => {
    if (res.verification_required) {
      setVerifyEmail(res.email ?? email);
      return;
    }
    login(res.token!, res.user!);
    router.replace("/");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const body =
        mode === "login"
          ? { email, password }
          : { name, email, password, program: program || null, year: year || null, interests };
      finish(await api<AuthResult>(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify(body) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const input =
    "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-indigo-400 focus:ring-4 focus:ring-indigo-500/10";

  return (
    <main className="flex h-full">
      {/* Brand panel */}
      <section className="relative hidden w-[52%] flex-col justify-between overflow-hidden bg-ink p-12 text-white lg:flex">
        <div className="animate-blob pointer-events-none absolute -left-24 -top-24 h-96 w-96 rounded-full bg-indigo-600/40 blur-3xl" />
        <div className="animate-blob pointer-events-none absolute -bottom-32 right-0 h-96 w-96 rounded-full bg-fuchsia-600/30 blur-3xl [animation-delay:-6s]" />
        <div className="animate-blob pointer-events-none absolute right-1/3 top-1/3 h-72 w-72 rounded-full bg-violet-500/20 blur-3xl [animation-delay:-3s]" />

        <div className="relative">
          <Logo />
        </div>

        <div className="relative max-w-lg">
          <h1 className="text-[44px] font-bold leading-[1.1] tracking-tight">
            Your research co-pilot for <span className="brand-text">ECE at IIT Roorkee</span>
          </h1>
          <p className="mt-4 text-lg text-slate-300">
            Discover professors, projects and openings that fit you, and turn curiosity into a conversation with faculty.
          </p>
          <div className="mt-10 space-y-5">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="flex gap-4">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/10">
                  <Icon className="h-5 w-5 text-indigo-200" />
                </div>
                <div>
                  <div className="font-semibold">{title}</div>
                  <div className="text-sm text-slate-400">{text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative grid grid-cols-3 gap-4">
          {[
            [status?.pages, "pages indexed"],
            [status?.faculty, "faculty profiles"],
            [status?.projects, "sponsored projects"],
          ].map(([v, label]) => (
            <div key={label as string} className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10 backdrop-blur">
              <div className="text-2xl font-bold">{v ?? "–"}</div>
              <div className="text-xs text-slate-400">{label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Form panel */}
      <section className="flex flex-1 items-center justify-center overflow-y-auto px-8 py-10">
        <div className="w-full max-w-md">
          {verifyEmail ? (
            <OtpStep
              email={verifyEmail}
              onBack={() => setVerifyEmail(null)}
              onVerified={(res) => {
                login(res.token!, res.user!);
                router.replace("/");
              }}
            />
          ) : (
            <>
              <h2 className="text-3xl font-bold tracking-tight text-slate-900">
                {mode === "login" ? "Welcome back" : "Create your account"}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                {mode === "login"
                  ? "Sign in to continue your research journey."
                  : "We'll verify your email with a one-time code."}
              </p>

              <div className="mt-8 grid grid-cols-2 rounded-xl bg-slate-200/60 p-1 text-sm font-medium">
                {(["login", "register"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => {
                      setMode(m);
                      setError("");
                    }}
                    className={`rounded-lg py-2 transition ${mode === m ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}
                  >
                    {m === "login" ? "Sign in" : "Create account"}
                  </button>
                ))}
              </div>

              <form onSubmit={submit} className="mt-6 space-y-4">
                {mode === "register" && (
                  <Field label="Full name">
                    <input className={input} value={name} onChange={(e) => setName(e.target.value)} required />
                  </Field>
                )}
                <Field label="Email">
                  <input className={input} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </Field>
                <Field label="Password" hint={mode === "register" ? "At least 8 characters" : undefined}>
                  <input
                    className={input}
                    type="password"
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    minLength={mode === "register" ? 8 : undefined}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </Field>

                {mode === "register" && (
                  <>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Programme">
                        <input className={input} placeholder="B.Tech ECE" value={program} onChange={(e) => setProgram(e.target.value)} />
                      </Field>
                      <Field label="Year / semester">
                        <input className={input} placeholder="3rd Year" value={year} onChange={(e) => setYear(e.target.value)} />
                      </Field>
                    </div>
                    <Field label="Research interests">
                      <InterestInput value={interests} onChange={setInterests} />
                    </Field>
                  </>
                )}

                {error && <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

                <button
                  type="submit"
                  disabled={busy}
                  className="brand-gradient w-full rounded-xl py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:opacity-95 disabled:opacity-60"
                >
                  {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
                </button>
              </form>
            </>
          )}
          <p className="mt-10 flex items-center justify-center gap-1.5 text-xs text-slate-400">
            <BookIcon className="h-3.5 w-3.5" /> Built on public data from the ECE Department website, IIT Roorkee
          </p>
        </div>
      </section>
    </main>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  );
}

const CODE_LENGTH = 6;

function OtpStep({
  email,
  onBack,
  onVerified,
}: {
  email: string;
  onBack: () => void;
  onVerified: (res: AuthResult) => void;
}) {
  const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(""));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(60);
  const [notice, setNotice] = useState("");
  const refs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    refs.current[0]?.focus();
  }, []);
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const verify = async (code: string) => {
    setBusy(true);
    setError("");
    try {
      onVerified(await api<AuthResult>("/api/auth/verify", { method: "POST", body: JSON.stringify({ email, code }) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
      setDigits(Array(CODE_LENGTH).fill(""));
      refs.current[0]?.focus();
    } finally {
      setBusy(false);
    }
  };

  const setAt = (i: number, value: string) => {
    const clean = value.replace(/\D/g, "");
    if (!clean) {
      setDigits((d) => d.map((x, j) => (j === i ? "" : x)));
      return;
    }
    // Typing or pasting several digits fills the following boxes too.
    const next = [...digits];
    for (let k = 0; k < clean.length && i + k < CODE_LENGTH; k++) next[i + k] = clean[k];
    setDigits(next);
    refs.current[Math.min(i + clean.length, CODE_LENGTH - 1)]?.focus();
    if (next.every(Boolean)) verify(next.join(""));
  };

  const resend = async () => {
    setError("");
    setNotice("");
    try {
      await api("/api/auth/resend", { method: "POST", body: JSON.stringify({ email }) });
      setCooldown(60);
      setNotice("A new code is on its way.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't resend the code");
    }
  };

  return (
    <div className="animate-fade-up">
      <div className="brand-gradient flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-lg shadow-indigo-500/30">
        <MailIcon className="h-6 w-6" />
      </div>
      <h2 className="mt-6 text-3xl font-bold tracking-tight text-slate-900">Check your email</h2>
      <p className="mt-2 text-sm text-slate-500">
        We sent a 6-digit code to <span className="font-semibold text-slate-800">{email}</span>. It expires in 10 minutes.
      </p>

      <div className="mt-8 flex justify-between gap-2">
        {digits.map((d, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            value={d}
            inputMode="numeric"
            autoComplete={i === 0 ? "one-time-code" : "off"}
            maxLength={CODE_LENGTH}
            disabled={busy}
            onChange={(e) => setAt(i, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
            }}
            className="h-14 w-14 rounded-2xl border-2 border-slate-200 bg-white text-center text-2xl font-bold text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10"
            aria-label={`Digit ${i + 1}`}
          />
        ))}
      </div>

      {error && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
      {notice && !error && <p className="mt-4 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</p>}

      <button
        onClick={() => verify(digits.join(""))}
        disabled={busy || digits.some((d) => !d)}
        className="brand-gradient mt-6 w-full rounded-xl py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 disabled:opacity-50"
      >
        {busy ? "Verifying…" : "Verify email"}
      </button>

      <div className="mt-5 flex items-center justify-between text-sm">
        <button onClick={onBack} className="text-slate-500 hover:text-slate-800">
          ← Use a different email
        </button>
        <button onClick={resend} disabled={cooldown > 0} className="font-medium text-navy disabled:text-slate-400">
          {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
        </button>
      </div>
    </div>
  );
}
