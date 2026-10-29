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
  const [forgot, setForgot] = useState(false);
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
    "w-full rounded-xl border border-[#d2d2d7] bg-white px-4 py-3 text-[15px] outline-none transition focus:border-navy focus:ring-4 focus:ring-navy/15";

  return (
    <main className="flex h-full">
      {/* Brand panel */}
      <section className="relative hidden w-[52%] flex-col justify-between bg-[#f5f5f7] p-14 lg:flex">
        <Logo />

        <div className="max-w-lg">
          <h1 className="headline text-[56px] leading-[1.05]">
            Your research copilot. <span className="brand-text">For ECE at IIT Roorkee.</span>
          </h1>
          <p className="mt-6 text-[19px] leading-relaxed text-[#6e6e73]">
            Discover professors, projects and openings that fit you, and turn curiosity into a conversation with faculty.
          </p>
          <div className="mt-12 space-y-6">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div key={title} className="flex gap-4">
                <Icon className="mt-0.5 h-6 w-6 shrink-0 text-navy" />
                <div>
                  <div className="text-[17px] font-semibold text-[#1d1d1f]">{title}</div>
                  <div className="text-[15px] text-[#6e6e73]">{text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-12">
          {[
            [status?.pages, "pages indexed"],
            [status?.faculty, "faculty profiles"],
            [status?.projects, "sponsored projects"],
          ].map(([v, label]) => (
            <div key={label as string}>
              <div className="headline text-[34px] leading-none">{v ?? "–"}</div>
              <div className="mt-1.5 text-sm text-[#86868b]">{label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Form panel */}
      <section className="flex flex-1 items-center justify-center overflow-y-auto bg-white px-8 py-10">
        <div className="w-full max-w-md">
          {forgot ? (
            <ForgotStep
              initialEmail={email}
              onBack={() => setForgot(false)}
              onDone={(res) => {
                login(res.token!, res.user!);
                router.replace("/");
              }}
            />
          ) : verifyEmail ? (
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
              <h2 className="text-3xl font-semibold tracking-tight text-slate-900">
                {mode === "login" ? "Welcome back" : "Create your account"}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                {mode === "login"
                  ? "Sign in to continue your research journey."
                  : "We'll verify your email with a one-time code."}
              </p>

              <div className="mt-8 grid grid-cols-2 rounded-full bg-[#f2f2f4] p-1 text-sm font-medium">
                {(["login", "register"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => {
                      setMode(m);
                      setError("");
                    }}
                    className={`rounded-full py-2 transition ${mode === m ? "bg-white text-[#1d1d1f] shadow-sm" : "text-[#6e6e73]"}`}
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
                <Field
                  label="Password"
                  hint={mode === "register" ? "At least 8 characters" : undefined}
                  action={
                    mode === "login" ? (
                      <button type="button" onClick={() => setForgot(true)} className="text-xs font-medium text-navy hover:underline">
                        Forgot password?
                      </button>
                    ) : undefined
                  }
                >
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
                  className="w-full rounded-full bg-navy py-3 text-[15px] font-medium text-white transition hover:bg-navy-dark transition hover:opacity-95 disabled:opacity-60"
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

function Field({
  label,
  hint,
  action,
  children,
}: {
  label: string;
  hint?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center justify-between text-sm font-medium text-slate-700">
        {label}
        {action}
      </span>
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
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-navy-soft text-navy">
        <MailIcon className="h-6 w-6" />
      </div>
      <h2 className="mt-6 text-3xl font-semibold tracking-tight text-slate-900">Check your email</h2>
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
            className="h-14 w-14 rounded-xl border border-[#d2d2d7] bg-white text-center text-2xl font-semibold text-[#1d1d1f] outline-none transition focus:border-navy focus:ring-4 focus:ring-navy/15"
            aria-label={`Digit ${i + 1}`}
          />
        ))}
      </div>

      {error && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
      {notice && !error && <p className="mt-4 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{notice}</p>}

      <button
        onClick={() => verify(digits.join(""))}
        disabled={busy || digits.some((d) => !d)}
        className="mt-6 w-full rounded-full bg-navy py-3 text-[15px] font-medium text-white transition hover:bg-navy-dark disabled:opacity-50"
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

function ForgotStep({
  initialEmail,
  onBack,
  onDone,
}: {
  initialEmail: string;
  onBack: () => void;
  onDone: (res: AuthResult) => void;
}) {
  const [email, setEmail] = useState(initialEmail);
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input =
    "w-full rounded-xl border border-[#d2d2d7] bg-white px-4 py-3 text-[15px] outline-none transition focus:border-navy focus:ring-4 focus:ring-navy/15";

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };
  const sendCode = () =>
    run(async () => {
      await api("/api/auth/forgot", { method: "POST", body: JSON.stringify({ email }) });
      setSent(true);
    });
  const reset = () =>
    run(async () => {
      onDone(await api<AuthResult>("/api/auth/reset", { method: "POST", body: JSON.stringify({ email, code, password }) }));
    });

  return (
    <div className="animate-fade-up">
      <h2 className="text-3xl font-semibold tracking-tight text-slate-900">Reset your password</h2>
      <p className="mt-2 text-sm text-slate-500">
        {sent
          ? `If ${email} has an account, a 6-digit code is on its way. It expires in 10 minutes.`
          : "Enter your account email and we'll send you a code."}
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (sent) reset();
          else sendCode();
        }}
        className="mt-8 space-y-4"
      >
        <Field label="Email">
          <input className={input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={sent} required />
        </Field>
        {sent && (
          <>
            <Field label="Code from the email">
              <input
                className={`${input} text-center text-lg font-bold tracking-[0.5em]`}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                required
              />
            </Field>
            <Field label="New password" hint="At least 8 characters">
              <input
                className={input}
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
          </>
        )}
        {error && <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-full bg-navy py-3 text-[15px] font-medium text-white transition hover:bg-navy-dark disabled:opacity-60"
        >
          {busy ? "Please wait…" : sent ? "Set new password" : "Send code"}
        </button>
      </form>
      <div className="mt-5 flex items-center justify-between text-sm">
        <button onClick={onBack} className="text-slate-500 hover:text-slate-800">
          ← Back to sign in
        </button>
        {sent && (
          <button onClick={sendCode} disabled={busy} className="font-medium text-navy disabled:text-slate-400">
            Resend code
          </button>
        )}
      </div>
    </div>
  );
}
