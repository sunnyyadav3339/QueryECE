"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import InterestInput from "@/components/InterestInput";
import { api, type User } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Mode = "login" | "register";

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

  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") {
        const res = await api<{ token: string; user: User }>("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        login(res.token, res.user);
      } else {
        const res = await api<{ token: string; user: User }>("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({ name, email, password }),
        });
        login(res.token, res.user);
        const updated = await api<User>("/api/me", {
          method: "PUT",
          body: JSON.stringify({ program: program || null, year: year || null, interests }),
        });
        login(res.token, updated);
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const input =
    "w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none transition focus:border-navy focus:ring-2 focus:ring-navy/10";

  return (
    <main className="flex min-h-full items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-navy">QueryECE</h1>
          <p className="mt-2 text-sm text-slate-500">
            Your research assistant for the ECE Department, IIT Roorkee
          </p>
        </div>

        <form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div className="mb-6 grid grid-cols-2 rounded-lg bg-slate-100 p-1 text-sm font-medium">
            {(["login", "register"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setMode(m);
                  setError("");
                }}
                className={`rounded-md py-2 transition ${mode === m ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}
              >
                {m === "login" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>

          <div className="space-y-4">
            {mode === "register" && (
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">Full name</span>
                <input className={input} value={name} onChange={(e) => setName(e.target.value)} required />
              </label>
            )}
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">Email</span>
              <input
                className={input}
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">Password</span>
              <input
                className={input}
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              {mode === "register" && <span className="mt-1 block text-xs text-slate-400">At least 8 characters</span>}
            </label>

            {mode === "register" && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-slate-700">Programme</span>
                    <input
                      className={input}
                      placeholder="B.Tech ECE"
                      value={program}
                      onChange={(e) => setProgram(e.target.value)}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-slate-700">Year / semester</span>
                    <input
                      className={input}
                      placeholder="2nd year"
                      value={year}
                      onChange={(e) => setYear(e.target.value)}
                    />
                  </label>
                </div>
                <div>
                  <span className="mb-2 block text-sm font-medium text-slate-700">Research interests</span>
                  <InterestInput value={interests} onChange={setInterests} />
                </div>
              </>
            )}
          </div>

          {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="mt-6 w-full rounded-lg bg-navy py-2.5 text-sm font-semibold text-white transition hover:bg-navy-dark disabled:opacity-60"
          >
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </div>
    </main>
  );
}
