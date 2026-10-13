"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import AppHeader from "@/components/AppHeader";
import Markdown from "@/components/Markdown";
import {
  api,
  streamMessage,
  type ChatMessage,
  type ChatSummary,
  type FacultyLite,
  type Source,
} from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

const LAST_CHAT_KEY = "queryece_last_chat";

interface UiMessage extends ChatMessage {
  status?: string;
  error?: string;
  streaming?: boolean;
}

/** Faculty named in full in an answer, for the "Draft email" shortcuts. */
function mentionedFaculty(content: string, faculty: FacultyLite[]): FacultyLite[] {
  // gpt-oss often puts non-breaking / narrow spaces inside names; \s matches them all.
  const text = content.replace(/\s+/g, " ").toLowerCase();
  return faculty
    .map((f) => ({ f, at: text.indexOf(f.name.toLowerCase()) }))
    .filter(({ at }) => at >= 0)
    .sort((a, b) => a.at - b.at)
    .slice(0, 3)
    .map(({ f }) => f);
}

function starterQuestions(interests: string[]): string[] {
  const base = [
    "Who is the Head of the ECE Department?",
    "What research groups and labs does the department have?",
    "Are there any open RA / JRF positions right now?",
  ];
  const personal = interests.slice(0, 3).map((i) => `Which professors work on ${i}?`);
  return [...personal, ...base].slice(0, 6);
}

export default function ChatPage() {
  const user = useRequireAuth();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [faculty, setFaculty] = useState<FacultyLite[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const openChat = useCallback(async (id: string | null) => {
    abortRef.current?.abort();
    setActiveId(id);
    setSidebarOpen(false);
    try {
      if (id) localStorage.setItem(LAST_CHAT_KEY, id);
      else localStorage.removeItem(LAST_CHAT_KEY);
    } catch {
      /* ignore */
    }
    if (!id) {
      setMessages([]);
      return;
    }
    const chat = await api<{ messages: ChatMessage[] }>(`/api/chats/${id}`);
    setMessages(chat.messages);
  }, []);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api<ChatSummary[]>("/api/chats").then((list) => {
      if (cancelled) return;
      setChats(list);
      let last: string | null = null;
      try {
        last = localStorage.getItem(LAST_CHAT_KEY);
      } catch {
        /* ignore */
      }
      if (last && list.some((c) => c.id === last)) openChat(last);
    });
    return () => {
      cancelled = true;
    };
  }, [user, openChat]);

  useEffect(() => {
    api<FacultyLite[]>("/api/faculty")
      .then(setFaculty)
      .catch(() => {});
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const updateLast = (fn: (m: UiMessage) => UiMessage) =>
    setMessages((prev) => [...prev.slice(0, -1), fn(prev[prev.length - 1])]);

  const send = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    setInput("");
    setSending(true);

    let chatId = activeId;
    try {
      if (!chatId) {
        const chat = await api<ChatSummary>("/api/chats", { method: "POST" });
        chatId = chat.id;
        setActiveId(chat.id);
        setChats((prev) => [chat, ...prev]);
        try {
          localStorage.setItem(LAST_CHAT_KEY, chat.id);
        } catch {
          /* ignore */
        }
      }
    } catch {
      setSending(false);
      return;
    }

    setMessages((prev) => [
      ...prev,
      { id: `u${Date.now()}`, role: "user", content, sources: [] },
      { id: `a${Date.now()}`, role: "assistant", content: "", sources: [], streaming: true, status: "Thinking" },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamMessage(
        chatId,
        content,
        (event) => {
          switch (event.type) {
            case "status":
              updateLast((m) => ({ ...m, status: event.text }));
              break;
            case "token":
              updateLast((m) => ({ ...m, content: m.content + event.text, status: undefined }));
              break;
            case "sources":
              updateLast((m) => ({ ...m, sources: event.sources as Source[] }));
              break;
            case "done":
              updateLast((m) => ({ ...m, id: event.message_id, streaming: false }));
              setChats((prev) => {
                const current = prev.find((c) => c.id === chatId);
                const rest = prev.filter((c) => c.id !== chatId);
                return current ? [{ ...current, title: event.title }, ...rest] : prev;
              });
              break;
            case "error":
              updateLast((m) => ({ ...m, error: event.text, streaming: false, status: undefined }));
              break;
          }
        },
        controller.signal,
      );
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        updateLast((m) => ({ ...m, error: "Connection lost. Please try again.", streaming: false }));
      }
    } finally {
      updateLast((m) => ({ ...m, streaming: false, status: undefined }));
      setSending(false);
      abortRef.current = null;
      textareaRef.current?.focus();
    }
  };

  const deleteChat = async (id: string) => {
    if (!confirm("Delete this conversation?")) return;
    await api(`/api/chats/${id}`, { method: "DELETE" });
    setChats((prev) => prev.filter((c) => c.id !== id));
    if (id === activeId) openChat(null);
  };

  if (!user) return null;

  const firstName = user.name.split(" ")[0];

  return (
    <div className="flex h-full flex-col">
      <AppHeader />
      <div className="flex min-h-0 flex-1">
        {/* Sidebar */}
        <aside
          className={`${
            sidebarOpen ? "flex" : "hidden"
          } absolute inset-y-16 left-0 z-20 w-72 flex-col border-r border-slate-200 bg-slate-50 md:static md:flex`}
        >
          <div className="p-3">
            <button
              onClick={() => openChat(null)}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-100"
            >
              <span className="text-lg leading-none">+</span> New chat
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-3">
            {chats.length === 0 && <p className="px-3 py-2 text-sm text-slate-400">No conversations yet</p>}
            {chats.map((c) => (
              <div
                key={c.id}
                className={`group mb-0.5 flex items-center rounded-lg ${
                  c.id === activeId ? "bg-white shadow-sm ring-1 ring-slate-200" : "hover:bg-slate-100"
                }`}
              >
                <button
                  onClick={() => openChat(c.id)}
                  className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm text-slate-700"
                  title={c.title}
                >
                  {c.title}
                </button>
                <button
                  onClick={() => deleteChat(c.id)}
                  className="mr-1 hidden rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-red-600 group-hover:block"
                  aria-label="Delete chat"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </aside>

        {/* Conversation */}
        <main className="relative flex min-w-0 flex-1 flex-col">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="absolute left-3 top-3 z-10 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 shadow-sm md:hidden"
          >
            Chats
          </button>
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
              <AssistantRow>
                <p className="text-[15px] leading-relaxed text-slate-700">
                  Hello, {firstName}. I&apos;m your QueryECE research assistant. I can help you find professors
                  matching your interests, look up sponsored projects and labs, and track RA / JRF openings in the
                  ECE department. What would you like to explore today?
                </p>
                {messages.length === 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {starterQuestions(user.interests).map((q) => (
                      <button
                        key={q}
                        onClick={() => send(q)}
                        className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 hover:border-navy hover:text-navy"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </AssistantRow>

              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="my-6 flex justify-end">
                    <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-navy-dark px-4 py-3 text-[15px] text-white">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <AssistantRow key={m.id}>
                    {m.content && <Markdown>{m.content}</Markdown>}
                    {m.streaming && m.status && (
                      <div className="flex items-center gap-2 text-sm text-slate-400">
                        <span className="h-2 w-2 animate-pulse rounded-full bg-navy" />
                        {m.status}…
                      </div>
                    )}
                    {m.error && (
                      <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{m.error}</p>
                    )}
                    {!m.streaming && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {mentionedFaculty(m.content, faculty).map((f) => (
                          <Link
                            key={f.id}
                            href={`/outreach?draft=${f.id}`}
                            className="inline-flex items-center gap-1 rounded-full border border-navy/20 bg-blue-50/50 px-2.5 py-1 text-xs font-medium text-navy hover:bg-blue-50"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M4 4h16v16H4z" />
                              <path d="m4 6 8 7 8-7" />
                            </svg>
                            Draft email to Prof. {f.name}
                          </Link>
                        ))}
                      </div>
                    )}
                    {m.sources.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {m.sources.map((s) => (
                          <a
                            key={s.url}
                            href={s.url}
                            target="_blank"
                            rel="noreferrer"
                            title={s.url}
                            className="inline-flex max-w-xs items-center gap-1 truncate rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600 hover:border-navy hover:text-navy"
                          >
                            <span className="font-semibold text-navy">[{s.n}]</span>
                            <span className="truncate">{s.title}</span>
                          </a>
                        ))}
                      </div>
                    )}
                  </AssistantRow>
                ),
              )}
              <div ref={endRef} />
            </div>
          </div>

          {/* Composer */}
          <div className="border-t border-slate-100 bg-gradient-to-t from-white via-white to-white/80 px-4 pb-4 pt-3">
            <div className="mx-auto max-w-3xl">
              <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm focus-within:border-navy/40">
                <textarea
                  ref={textareaRef}
                  rows={1}
                  value={input}
                  onChange={(e) => {
                    setInput(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  placeholder="Ask QueryECE about professors, labs, projects or openings…"
                  className="block max-h-40 w-full resize-none bg-transparent px-1 text-[15px] text-slate-800 outline-none placeholder:text-slate-400"
                />
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-xs text-slate-400">Enter to send · Shift+Enter for a new line</span>
                  {sending ? (
                    <button
                      onClick={() => abortRef.current?.abort()}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                    >
                      Stop
                    </button>
                  ) : (
                    <button
                      onClick={() => send()}
                      disabled={!input.trim()}
                      className="flex h-9 w-9 items-center justify-center rounded-lg bg-navy text-white transition hover:bg-navy-dark disabled:bg-slate-200 disabled:text-slate-400"
                      aria-label="Send"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
              <p className="mt-2 text-center text-xs text-slate-400">
                QueryECE answers from the ECE department website and can make mistakes. Verify before sending outreach.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function AssistantRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-6 flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy text-sm font-semibold text-white">
        Q
      </div>
      <div className="min-w-0 flex-1 pt-0.5">{children}</div>
    </div>
  );
}
