"use client";

import { useState, useEffect, useRef } from "react";

interface FacultyMember {
  id: string;
  name: string;
  designation: string;
  email: string;
  phone?: string;
  website?: string;
  profile_url: string;
  research_interests: string[];
  education: string[];
  cv_links: string[];
  bio_summary: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  faculty?: FacultyMember[];
  announcements?: string[];
  links?: { text: string; url: string }[];
  time: string;
}

const API_BASE = "http://localhost:8000";

const SAMPLE_QUESTIONS = [
  "Who is working on VLSI design?",
  "Who is the Head of the Department?",
  "Tell me about 6G and wearable devices",
  "Research in Brain-Machine Interfaces & AI",
  "M.Tech (VLSI) for Industry Professionals",
  "Who specializes in RF and Antennas?",
];

export default function Home() {
  const [activeTab, setActiveTab] = useState<"chat" | "directory">("chat");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [allFaculty, setAllFaculty] = useState<FacultyMember[]>([]);
  const [facultyFilter, setFacultyFilter] = useState("");
  const [desigFilter, setDesigFilter] = useState("all");
  const [fetchingFaculty, setFetchingFaculty] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (activeTab === "directory" && allFaculty.length === 0) {
      loadFacultyDirectory();
    }
  }, [activeTab, allFaculty.length]);

  const loadFacultyDirectory = async () => {
    setFetchingFaculty(true);
    try {
      const res = await fetch(`${API_BASE}/api/faculty`);
      if (res.ok) {
        const data = await res.json();
        setAllFaculty(data);
      }
    } catch (err) {
      console.error("Failed to load faculty:", err);
    } finally {
      setFetchingFaculty(false);
    }
  };

  const handleSend = async (questionText?: string) => {
    const textToSend = (questionText ?? query).trim();
    if (!textToSend || loading) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      text: textToSend,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuery("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: textToSend, top_k: 4 }),
      });

      if (!res.ok) throw new Error(`Server returned ${res.status}`);

      const data = await res.json();

      const assistantMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        text: data.answer || "No response received.",
        faculty: data.faculty || [],
        announcements: data.announcements || [],
        links: data.links || [],
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error("Query failed:", err);
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        text: "Sorry, I couldn't reach the QueryECE backend. Please ensure the backend container is running at `http://localhost:8000`.",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const filteredFaculty = allFaculty.filter((f) => {
    const matchesText =
      !facultyFilter ||
      f.name.toLowerCase().includes(facultyFilter.toLowerCase()) ||
      f.email.toLowerCase().includes(facultyFilter.toLowerCase()) ||
      f.research_interests.some((r) => r.toLowerCase().includes(facultyFilter.toLowerCase()));

    const matchesDesig =
      desigFilter === "all" ||
      f.designation.toLowerCase().includes(desigFilter.toLowerCase());

    return matchesText && matchesDesig;
  });

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 font-sans">
      {/* Header */}
      <header className="sticky top-0 z-30 backdrop-blur-md bg-white/80 dark:bg-zinc-900/80 border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shadow-md shadow-blue-500/20">
              <span className="text-white text-xl font-extrabold tracking-tight">Q</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-xl tracking-tight">
                  Query<span className="text-blue-600 dark:text-blue-400">ECE</span>
                </span>
                <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300">
                  IIT Roorkee
                </span>
              </div>
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400 hidden sm:block">
                Electronics &amp; Communication Engineering Department Assistant
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center bg-zinc-100 dark:bg-zinc-800 p-1 rounded-xl text-sm font-medium">
            <button
              onClick={() => setActiveTab("chat")}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg transition-all ${
                activeTab === "chat"
                  ? "bg-white dark:bg-zinc-900 text-blue-600 dark:text-blue-400 shadow-sm font-semibold"
                  : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                />
              </svg>
              <span>Ask AI</span>
            </button>
            <button
              onClick={() => setActiveTab("directory")}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg transition-all ${
                activeTab === "directory"
                  ? "bg-white dark:bg-zinc-900 text-blue-600 dark:text-blue-400 shadow-sm font-semibold"
                  : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
                />
              </svg>
              <span>Faculty Directory</span>
              <span className="text-xs bg-zinc-200 dark:bg-zinc-700 px-1.5 py-0.2 rounded-full">
                38
              </span>
            </button>
          </nav>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-6 flex flex-col">
        {activeTab === "chat" ? (
          <div className="flex-1 flex flex-col justify-between max-w-4xl mx-auto w-full">
            {/* Conversation list */}
            {messages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center my-auto py-12">
                <div className="h-16 w-16 rounded-2xl bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center mb-6 shadow-xl shadow-blue-500/20">
                  <span className="text-white text-3xl font-extrabold">Q</span>
                </div>
                <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">
                  How can I help you explore{" "}
                  <span className="text-blue-600 dark:text-blue-400">ECE Department</span>?
                </h1>
                <p className="text-zinc-600 dark:text-zinc-400 max-w-xl text-base mb-8">
                  Ask about faculty research domains, professors, contact details, official
                  announcements, or academic programmes at IIT Roorkee.
                </p>

                {/* Suggested Questions Grid */}
                <div className="w-full max-w-2xl">
                  <p className="text-xs uppercase tracking-wider font-semibold text-zinc-400 dark:text-zinc-500 mb-3">
                    Suggested Questions
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-left">
                    {SAMPLE_QUESTIONS.map((q) => (
                      <button
                        key={q}
                        onClick={() => handleSend(q)}
                        className="p-3.5 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 hover:border-blue-400 dark:hover:border-blue-600 hover:shadow-sm transition-all group text-sm flex items-center justify-between"
                      >
                        <span className="text-zinc-700 dark:text-zinc-300 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                          {q}
                        </span>
                        <svg
                          className="w-4 h-4 text-zinc-400 group-hover:text-blue-500 transition-colors shrink-0 ml-2"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-6 pb-6">
                {messages.map((msg) => (
                  <div key={msg.id} className="space-y-4">
                    {msg.role === "user" ? (
                      <div className="flex justify-end">
                        <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-tr-sm bg-blue-600 text-white px-5 py-3.5 shadow-sm">
                          <p className="text-sm sm:text-base leading-relaxed">{msg.text}</p>
                          <span className="text-[10px] text-blue-200 block text-right mt-1">
                            {msg.time}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-3.5">
                        <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shrink-0 shadow-sm mt-1">
                          <span className="text-white text-xs font-bold">Q</span>
                        </div>
                        <div className="flex-1 space-y-4 max-w-full overflow-hidden">
                          {/* Answer Box */}
                          <div className="rounded-2xl rounded-tl-sm bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-5 shadow-sm">
                            <MarkdownViewer content={msg.text} />
                            <span className="text-[10px] text-zinc-400 block text-right mt-2">
                              {msg.time}
                            </span>
                          </div>

                          {/* Faculty Cards Grid */}
                          {msg.faculty && msg.faculty.length > 0 && (
                            <div>
                              <p className="text-xs uppercase tracking-wider font-semibold text-zinc-400 dark:text-zinc-500 mb-2.5">
                                Relevant Faculty Members ({msg.faculty.length})
                              </p>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {msg.faculty.map((fac) => (
                                  <FacultyCard key={fac.id || fac.email} faculty={fac} />
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Official Links */}
                          {msg.links && msg.links.length > 0 && (
                            <div className="p-3.5 rounded-xl bg-blue-50 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-900/50">
                              <p className="text-xs font-semibold text-blue-900 dark:text-blue-300 mb-2">
                                Official Department Links:
                              </p>
                              <div className="flex flex-wrap gap-2">
                                {msg.links.map((l, idx) => (
                                  <a
                                    key={idx}
                                    href={l.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-xs text-blue-700 dark:text-blue-400 hover:underline flex items-center gap-1 bg-white dark:bg-zinc-900 px-2.5 py-1 rounded-md border border-blue-200 dark:border-blue-800"
                                  >
                                    <span>{l.text}</span>
                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                    </svg>
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {/* Loading State */}
                {loading && (
                  <div className="flex gap-3.5">
                    <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shrink-0 shadow-sm mt-1 animate-pulse">
                      <span className="text-white text-xs font-bold">Q</span>
                    </div>
                    <div className="rounded-2xl rounded-tl-sm bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-5 shadow-sm flex items-center gap-3">
                      <div className="w-2.5 h-2.5 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.3s]"></div>
                      <div className="w-2.5 h-2.5 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.15s]"></div>
                      <div className="w-2.5 h-2.5 rounded-full bg-blue-600 animate-bounce"></div>
                      <span className="text-sm text-zinc-500 dark:text-zinc-400 ml-1">
                        Searching ECE directory and analyzing data...
                      </span>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}

            {/* Input Bar */}
            <div className="sticky bottom-4 z-20 pt-2">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
                className="flex items-center gap-2 p-1.5 rounded-2xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg shadow-zinc-200/50 dark:shadow-none focus-within:border-blue-500 dark:focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 transition-all"
              >
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ask anything about faculty, research areas, courses, or labs..."
                  className="flex-1 bg-transparent px-4 py-2.5 text-sm sm:text-base outline-none text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400"
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={!query.trim() || loading}
                  className="h-10 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium text-sm flex items-center gap-1.5 transition-all shrink-0"
                >
                  <span>Send</span>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </button>
              </form>
            </div>
          </div>
        ) : (
          /* Faculty Directory Tab */
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-zinc-900 p-5 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm">
              <div>
                <h2 className="text-xl font-bold">ECE Department Faculty</h2>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  Showing {filteredFaculty.length} of {allFaculty.length} professors
                </p>
              </div>

              {/* Filters */}
              <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
                <input
                  type="text"
                  placeholder="Search by name, interest, or email..."
                  value={facultyFilter}
                  onChange={(e) => setFacultyFilter(e.target.value)}
                  className="px-3.5 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm outline-none focus:border-blue-500 w-full sm:w-64"
                />
                <select
                  value={desigFilter}
                  onChange={(e) => setDesigFilter(e.target.value)}
                  className="px-3 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 text-sm outline-none focus:border-blue-500"
                >
                  <option value="all">All Designations</option>
                  <option value="Head">Head of Department</option>
                  <option value="Professor">Professor</option>
                  <option value="Associate">Associate Professor</option>
                  <option value="Assistant">Assistant Professor</option>
                </select>
              </div>
            </div>

            {fetchingFaculty ? (
              <div className="text-center py-20 text-zinc-400">Loading faculty directory...</div>
            ) : filteredFaculty.length === 0 ? (
              <div className="text-center py-20 text-zinc-500">
                No faculty members match the filter criteria.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredFaculty.map((fac) => (
                  <FacultyCard key={fac.id || fac.email} faculty={fac} />
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

// Subcomponent: Faculty Card
function FacultyCard({ faculty }: { faculty: FacultyMember }) {
  const getBadgeColor = (desig: string) => {
    const d = desig.toLowerCase();
    if (d.includes("head")) return "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300";
    if (d.includes("associate")) return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300";
    if (d.includes("assistant")) return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300";
    return "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300";
  };

  const initials = faculty.name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0])
    .join("")
    .toUpperCase();

  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4.5 shadow-sm hover:shadow-md hover:border-zinc-300 dark:hover:border-zinc-700 transition-all flex flex-col justify-between">
      <div>
        <div className="flex items-start gap-3 mb-3">
          <div className="h-11 w-11 rounded-xl bg-gradient-to-tr from-slate-200 to-slate-300 dark:from-zinc-700 dark:to-zinc-800 flex items-center justify-center font-bold text-zinc-700 dark:text-zinc-200 text-sm shrink-0">
            {initials || "DR"}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold text-base leading-tight truncate">{faculty.name}</h3>
            <span
              className={`inline-block text-[11px] font-medium px-2 py-0.5 rounded-md mt-1 ${getBadgeColor(
                faculty.designation
              )}`}
            >
              {faculty.designation}
            </span>
          </div>
        </div>

        {/* Email & Phone */}
        <div className="space-y-1 text-xs text-zinc-600 dark:text-zinc-400 mb-3">
          {faculty.email && (
            <div className="flex items-center gap-1.5 truncate">
              <svg className="w-3.5 h-3.5 text-zinc-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <a href={`mailto:${faculty.email}`} className="hover:text-blue-600 truncate underline">
                {faculty.email}
              </a>
            </div>
          )}
          {faculty.phone && (
            <div className="flex items-center gap-1.5 text-[11px]">
              <svg className="w-3.5 h-3.5 text-zinc-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
              </svg>
              <span>{faculty.phone}</span>
            </div>
          )}
        </div>

        {/* Research Interests Tags */}
        {faculty.research_interests && faculty.research_interests.length > 0 && (
          <div className="mb-4">
            <p className="text-[10px] uppercase font-semibold text-zinc-400 dark:text-zinc-500 mb-1.5">
              Research Interests
            </p>
            <div className="flex flex-wrap gap-1">
              {faculty.research_interests.slice(0, 3).map((item, idx) => (
                <span
                  key={idx}
                  className="text-[11px] bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 px-2 py-0.5 rounded-md"
                >
                  {item}
                </span>
              ))}
              {faculty.research_interests.length > 3 && (
                <span className="text-[10px] text-zinc-400 self-center">
                  +{faculty.research_interests.length - 3} more
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800/80 flex items-center gap-2">
        {faculty.profile_url && (
          <a
            href={faculty.profile_url}
            target="_blank"
            rel="noreferrer"
            className="flex-1 text-center py-1.5 px-3 rounded-lg text-xs font-medium border border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors flex items-center justify-center gap-1"
          >
            <span>Profile</span>
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        )}
        {faculty.cv_links && faculty.cv_links.length > 0 && (
          <a
            href={faculty.cv_links[0]}
            target="_blank"
            rel="noreferrer"
            className="py-1.5 px-3 rounded-lg text-xs font-medium bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/60 transition-colors flex items-center gap-1"
          >
            <span>CV</span>
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </a>
        )}
        {faculty.website && (
          <a
            href={faculty.website}
            target="_blank"
            rel="noreferrer"
            className="py-1.5 px-2.5 rounded-lg text-xs font-medium text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
            title="Personal / Lab Website"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
            </svg>
          </a>
        )}
      </div>
    </div>
  );
}

// Subcomponent: Lightweight Markdown Viewer
function MarkdownViewer({ content }: { content: string }) {
  const lines = content.split("\n");

  const renderFormatted = (text: string) => {
    // Basic regex parser for bold, inline links
    const parts = [];
    let remaining = text;
    let keyIdx = 0;

    while (remaining.length > 0) {
      // Check link [text](url)
      const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/);
      if (linkMatch) {
        parts.push(
          <a
            key={keyIdx++}
            href={linkMatch[2]}
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
          >
            {linkMatch[1]}
          </a>
        );
        remaining = remaining.slice(linkMatch[0].length);
        continue;
      }

      // Check bold **text**
      const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/);
      if (boldMatch) {
        parts.push(
          <strong key={keyIdx++} className="font-semibold text-zinc-950 dark:text-white">
            {boldMatch[1]}
          </strong>
        );
        remaining = remaining.slice(boldMatch[0].length);
        continue;
      }

      // Plain char
      const nextSpecial = remaining.search(/(\*\*|\[)/);
      if (nextSpecial === -1) {
        parts.push(remaining);
        break;
      } else if (nextSpecial === 0) {
        parts.push(remaining[0]);
        remaining = remaining.slice(1);
      } else {
        parts.push(remaining.slice(0, nextSpecial));
        remaining = remaining.slice(nextSpecial);
      }
    }

    return parts;
  };

  return (
    <div className="space-y-2 text-sm sm:text-base leading-relaxed">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={idx} className="h-2" />;

        if (trimmed.startsWith("### ")) {
          return (
            <h4 key={idx} className="text-base font-bold text-zinc-900 dark:text-zinc-100 mt-3 mb-1">
              {trimmed.slice(4)}
            </h4>
          );
        }

        if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
          return (
            <div key={idx} className="flex items-start gap-2 pl-2">
              <span className="text-blue-600 dark:text-blue-400 mt-1 text-sm">•</span>
              <div className="flex-1">{renderFormatted(trimmed.slice(2))}</div>
            </div>
          );
        }

        if (trimmed.startsWith("    * ") || trimmed.startsWith("  - ")) {
          return (
            <div key={idx} className="flex items-start gap-2 pl-6 text-sm text-zinc-600 dark:text-zinc-300">
              <span className="text-zinc-400 mt-1 text-xs">◦</span>
              <div className="flex-1">{renderFormatted(trimmed.replace(/^(\s*[-*]\s*)/, ""))}</div>
            </div>
          );
        }

        return <p key={idx}>{renderFormatted(line)}</p>;
      })}
    </div>
  );
}
