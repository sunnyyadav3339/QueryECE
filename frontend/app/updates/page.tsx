"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import UpdateList from "@/components/UpdateList";
import { api, type UpdateItem } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";

const KINDS: [string | null, string][] = [
  [null, "Everything"],
  ["new_opening", "Openings"],
  ["new_project", "Projects"],
  ["updated_page", "Updated pages"],
  ["new_page", "New pages"],
];

export default function UpdatesPage() {
  const user = useRequireAuth();
  const [items, setItems] = useState<UpdateItem[] | null>(null);
  const [forYou, setForYou] = useState(false);
  const [kind, setKind] = useState<string | null>(null);

  const interestsKey = user?.interests.join("|");
  useEffect(() => {
    if (!user) return;
    api<UpdateItem[]>("/api/updates?days=90").then(setItems);
  }, [user, interestsKey]);

  if (!user) return null;
  const shown = (items ?? []).filter((u) => (!forYou || u.for_you) && (!kind || u.kind === kind));
  const mine = (items ?? []).filter((u) => u.for_you).length;

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-[860px] px-4 pb-16 pt-6 md:px-6 md:pt-10">
          <h1 className="headline text-[30px] leading-tight md:text-[40px]">
            What&apos;s new. <span className="brand-text">Without checking every page.</span>
          </h1>
          <p className="mt-3 max-w-2xl text-[17px] text-[#6e6e73]">
            Every crawl of the ECE website is compared with the last one. New openings, new sponsored projects and changed
            pages show up here, and the ones matching your interests are marked for you.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-2">
            <button
              onClick={() => setForYou((v) => !v)}
              className={`rounded-full px-4 py-1.5 text-sm transition ${
                forYou ? "bg-navy text-white" : "bg-black/[0.04] text-[#1d1d1f] hover:bg-black/[0.08]"
              }`}
            >
              For you{items ? ` · ${mine}` : ""}
            </button>
            <span className="mx-1 h-5 w-px bg-black/10" />
            {KINDS.map(([k, label]) => (
              <button
                key={label}
                onClick={() => setKind(k)}
                className={`rounded-full px-4 py-1.5 text-sm transition ${
                  kind === k ? "bg-[#1d1d1f] text-white" : "bg-black/[0.04] text-[#1d1d1f] hover:bg-black/[0.08]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="card mt-6 overflow-hidden">
            {items === null && <p className="p-6 text-sm text-[#86868b]">Loading…</p>}
            {items && shown.length === 0 && (
              <p className="p-10 text-center text-sm text-[#6e6e73]">
                Nothing yet. Changes appear here after the weekly crawl.
              </p>
            )}
            {shown.length > 0 && <UpdateList items={shown} />}
          </div>
          <p className="mt-4 text-xs text-[#86868b]">
            {user.email_alerts
              ? "You get a daily email when something new matches your interests. Change this on your Profile page."
              : "Email alerts are off. Turn them on from your Profile page."}
          </p>
        </div>
      </div>
    </AppShell>
  );
}
