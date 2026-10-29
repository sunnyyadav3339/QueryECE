"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import { ArrowRightIcon, BookIcon, ChatIcon, MailIcon, PlusIcon, SendIcon, SparkIcon, TrashIcon } from "@/components/icons";
import Markdown from "@/components/Markdown";
import { UserAvatar } from "@/components/ui";
import {
  api,
  streamMessage,
  type ChatMessage,
  type ChatSummary,
  type FacultyLite,
  type HomeData,
  type Source,
} from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

const LAST_CHAT_KEY = "queryece_last_chat";

interface UiMessage extends ChatMessage {
  status?: string;
  error?: string;
  streaming?: boolean;
  suggestions?: string[];
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

function pendingQuestion(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("q");
}

export default function ChatPage() {
  const user = useRequireAuth();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [faculty, setFaculty] = useState<FacultyLite[]>([]);
  const [starters, setStarters] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sendRef = useRef<(text?: string) => void>(() => {});

  const openChat = useCallback(async (id: string | null) => {
    abortRef.current?.abort();
    setActiveId(id);
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
    const q = pendingQuestion();
    api<ChatSummary[]>("/api/chats").then((list) => {
      if (cancelled) return;
      setChats(list);
      if (q) {
        // Arrived from Home / a professor card: ask in a fresh chat.
        window.history.replaceState(null, "", "/chat");
        Promise.resolve().then(() => sendRef.current(q));
        return;
      }
      let last: string | null = null;
      try {
        last = localStorage.getItem(LAST_CHAT_KEY);
      } catch {
        /* ignore */
      }
      if (last && list.some((c) => c.id === last)) openChat(last);
    });
    api<FacultyLite[]>("/api/faculty").then(setFaculty).catch(() => {});
    api<HomeData>("/api/home")
      .then((h) => setStarters(h.questions))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user, openChat]);

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
      ...prev.map((m) => ({ ...m, suggestions: undefined })),
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
            case "suggestions":
              updateLast((m) => ({ ...m, suggestions: event.items }));
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
  useEffect(() => {
    sendRef.current = send;
  });

  const deleteChat = async (id: string) => {
    if (!confirm("Delete this conversation?")) return;
    await api(`/api/chats/${id}`, { method: "DELETE" });
    setChats((prev) => prev.filter((c) => c.id !== id));
    if (id === activeId) openChat(null);
  };

  if (!user) return null;
  const firstName = user.name.split(" ")[0];
  const lastIdx = messages.length - 1;

  return (
    <AppShell>
      <div className="flex h-full">
        {/* History */}
        <aside className="flex w-72 shrink-0 flex-col border-r border-black/[0.06] bg-white/70">
          <div className="p-4">
            <button
              onClick={() => openChat(null)}
              className="brand-gradient flex w-full items-center justify-center gap-2 rounded-full px-3 py-2.5 text-sm font-semibold text-white transition hover:opacity-95"
            >
              <PlusIcon className="h-4 w-4" /> New chat
            </button>
          </div>
          <div className="px-5 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Recent</div>
          <div className="flex-1 overflow-y-auto px-3 pb-4">
            {chats.length === 0 && <p className="px-3 py-2 text-sm text-slate-400">No conversations yet</p>}
            {chats.map((c) => (
              <div
                key={c.id}
                className={`group mb-0.5 flex items-center rounded-xl ${
                  c.id === activeId ? "bg-black/[0.05] text-[#1d1d1f]" : "text-[#515154] hover:bg-black/[0.03]"
                }`}
              >
                <button onClick={() => openChat(c.id)} className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2.5 text-left text-sm" title={c.title}>
                  <ChatIcon className={`h-4 w-4 shrink-0 ${c.id === activeId ? "text-indigo-500" : "text-slate-400"}`} />
                  <span className="truncate">{c.title}</span>
                </button>
                <button
                  onClick={() => deleteChat(c.id)}
                  className="mr-1.5 hidden rounded-lg p-1.5 text-slate-400 hover:bg-white hover:text-red-600 group-hover:block"
                  aria-label="Delete chat"
                >
                  <TrashIcon className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </aside>

        {/* Conversation */}
        <section className="relative flex min-w-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-4xl px-8 pb-10 pt-8">
              {messages.length === 0 ? (
                <div className="animate-fade-up pt-10 text-center">
                  <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[18px] bg-[#1d1d1f] text-2xl font-semibold text-white">
                    Q
                  </div>
                  <h1 className="headline mt-6 text-[40px] leading-tight">
                    Hi {firstName}. <span className="brand-text">What are you curious about?</span>
                  </h1>
                  <p className="mx-auto mt-3 max-w-xl text-[15px] text-slate-500">
                    I answer from the ECE department website (refreshed weekly) and tailor answers to your interests
                    {user.interests.length ? `: ${user.interests.slice(0, 3).join(", ")}` : ""}.
                  </p>
                  <div className="mt-10 grid grid-cols-2 gap-3 text-left">
                    {starters.slice(0, 6).map((q, i) => (
                      <button
                        key={q}
                        onClick={() => send(q)}
                        className="card card-hover animate-fade-up flex items-start gap-3 p-4 text-left"
                        style={{ animationDelay: `${i * 40}ms` }}
                      >
                        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                          <SparkIcon className="h-4 w-4" />
                        </span>
                        <span className="text-sm font-medium text-slate-700">{q}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m, i) =>
                  m.role === "user" ? (
                    <div key={m.id} className="animate-fade-up my-6 flex justify-end gap-3">
                      <div className="brand-gradient max-w-[78%] whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-3 text-[15px] text-white">
                        {m.content}
                      </div>
                      <UserAvatar name={user.name} className="h-8 w-8 text-xs" />
                    </div>
                  ) : (
                    <div key={m.id} className="animate-fade-up my-6 flex gap-3">
                      <div className="brand-gradient flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-black text-white">
                        Q
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="card px-5 py-4">
                          {m.content && <Markdown>{m.content}</Markdown>}
                          {m.streaming && m.status && (
                            <div className="flex items-center gap-2 text-sm font-medium">
                              <span className="flex gap-1">
                                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-500" />
                                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-500 [animation-delay:120ms]" />
                                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-fuchsia-500 [animation-delay:240ms]" />
                              </span>
                              <span className="shimmer-text">{m.status}…</span>
                            </div>
                          )}
                          {m.error && <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{m.error}</p>}

                          {!m.streaming && mentionedFaculty(m.content, faculty).length > 0 && (
                            <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                              {mentionedFaculty(m.content, faculty).map((f) => (
                                <Link
                                  key={f.id}
                                  href={`/outreach?draft=${f.id}`}
                                  className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
                                >
                                  <MailIcon className="h-3.5 w-3.5" /> Draft email to Prof. {f.name}
                                </Link>
                              ))}
                            </div>
                          )}
                        </div>

                        {m.sources.length > 0 && (
                          <div className="mt-2.5 flex flex-wrap gap-1.5">
                            {m.sources.map((s) => (
                              <a
                                key={s.url}
                                href={s.url}
                                target="_blank"
                                rel="noreferrer"
                                title={s.url}
                                className="inline-flex max-w-[16rem] items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 transition hover:border-indigo-200 hover:text-indigo-700"
                              >
                                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded bg-indigo-100 text-[10px] font-bold text-indigo-700">
                                  {s.n}
                                </span>
                                <BookIcon className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                                <span className="truncate">{s.title}</span>
                              </a>
                            ))}
                          </div>
                        )}

                        {i === lastIdx && m.suggestions && m.suggestions.length > 0 && !sending && (
                          <div className="mt-4">
                            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                              Suggested for you
                            </div>
                            <div className="flex flex-col items-start gap-1.5">
                              {m.suggestions.map((q) => (
                                <button
                                  key={q}
                                  onClick={() => send(q)}
                                  className="group inline-flex items-center gap-2 rounded-xl border border-indigo-100 bg-white px-3 py-2 text-left text-sm text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50"
                                >
                                  <ArrowRightIcon className="h-3.5 w-3.5 text-indigo-400 group-hover:text-indigo-600" />
                                  {q}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ),
                )
              )}
              <div ref={endRef} />
            </div>
          </div>

          {/* Composer */}
          <div className="px-8 pb-6 pt-2">
            <div className="mx-auto max-w-4xl">
              <div className="card flex items-end gap-3 p-3 focus-within:border-indigo-300">
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
                  placeholder="Ask about professors, labs, projects or openings…"
                  className="block max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] text-slate-800 outline-none placeholder:text-slate-400"
                />
                {sending ? (
                  <button
                    onClick={() => abortRef.current?.abort()}
                    className="h-10 rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50"
                  >
                    Stop
                  </button>
                ) : (
                  <button
                    onClick={() => send()}
                    disabled={!input.trim()}
                    className="brand-gradient flex h-10 w-10 items-center justify-center rounded-full text-white transition disabled:opacity-40 disabled:shadow-none"
                    aria-label="Send"
                  >
                    <SendIcon className="h-4 w-4" />
                  </button>
                )}
              </div>
              <p className="mt-2 text-center text-[11px] text-slate-400">
                Answers come from the ECE department website and can contain mistakes. Check before you email a professor.
              </p>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
