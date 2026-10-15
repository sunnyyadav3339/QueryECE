export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const TOKEN_KEY = "queryece_token";

export interface User {
  id: number;
  name: string;
  email: string;
  program: string | null;
  year: string | null;
  bio: string | null;
  interests: string[];
  stats: { chats: number; questions: number };
}

export interface ChatSummary {
  id: string;
  title: string;
  updated_at: string;
}

export interface Source {
  n: number;
  title: string;
  url: string;
}

export interface ChatMessage {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
}

export interface Opportunity {
  id: number;
  kind: string;
  title: string;
  department: string | null;
  is_ece: boolean;
  posted_on: string | null;
  deadline: string | null;
  url: string;
  match: number | null;
  matched_interest: string | null;
}

export interface FacultyLite {
  id: number;
  name: string;
  designation: string | null;
  email: string | null;
  interests: string | null;
}

export interface MatchReason {
  interest: string;
  topic: string;
}

/** A professor as ranked for the signed-in student. */
export interface FacultyCard {
  id: number;
  name: string;
  designation: string | null;
  email: string | null;
  interests: string | null;
  image_url: string | null;
  profile_url: string | null;
  website: string | null;
  projects: number;
  match: number;
  matched: string[];
  reasons: MatchReason[];
}

export interface FacultyDetail {
  id: number;
  name: string;
  designation: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  interests: string | null;
  image_url: string | null;
  profile_url: string | null;
  projects: { title: string; agency: string | null; year: string | null; co_pi: string | null }[];
  startups: { name: string; website: string | null }[];
}

export interface HomeData {
  matches: FacultyCard[];
  openings: Opportunity[];
  outreach: { total: number; by_status: Record<string, number>; follow_up_due: string[] };
  questions: string[];
}

export interface AuthResult {
  token?: string;
  user?: User;
  verification_required?: boolean;
  email?: string;
  resend_after?: number;
}

export type OutreachStatus = "drafted" | "sent" | "replied" | "meeting" | "accepted" | "rejected";

export interface OutreachCard {
  id: number;
  faculty_id: number;
  professor_name: string;
  professor_email: string | null;
  purpose: string | null;
  subject: string;
  body: string;
  sent: { subject: string; body: string; sent_on: string }[];
  status: OutreachStatus;
  notes: string;
  sent_on: string | null;
  follow_up_on: string | null;
  updated_at: string;
}

export type StreamEvent =
  | { type: "status"; text: string }
  | { type: "token"; text: string }
  | { type: "sources"; sources: Source[] }
  | { type: "done"; message_id: number; title: string }
  | { type: "suggestions"; items: string[] }
  | { type: "error"; text: string };

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session-only login */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join(", ")
            : message;
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

/** POST a message and invoke onEvent for each server-sent event. */
export async function streamMessage(
  chatId: string,
  content: string,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
) {
  const res = await fetch(`${API_BASE}/api/chats/${chatId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, res.status === 401 ? "Session expired" : "Request failed");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const data = frame
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("");
      if (data) onEvent(JSON.parse(data) as StreamEvent);
    }
  }
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

/** Link that opens a new chat and asks `q` straight away. */
export const askUrl = (q: string) => `/chat?q=${encodeURIComponent(q)}`;
