import type { UpdateItem } from "@/lib/api";

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "";

/** Feed rows for "What's new" (full page and the Home card). */
export default function UpdateList({ items, compact = false }: { items: UpdateItem[]; compact?: boolean }) {
  return (
    <ul className="divide-y divide-black/[0.06]">
      {items.map((u) => {
        const Row = u.url ? "a" : "div";
        return (
          <li key={u.id}>
            <Row
              {...(u.url ? { href: u.url, target: "_blank", rel: "noreferrer" } : {})}
              className={`block ${compact ? "py-3" : "px-6 py-4"} transition ${u.url ? "hover:bg-black/[0.02]" : ""}`}
            >
              <div className="flex items-center gap-2 text-xs">
                <span className="font-medium text-[#6e6e73]">{u.label}</span>
                {u.for_you && <span className="font-medium text-navy">· For you · {u.matched_interest}</span>}
                <span className="ml-auto text-[#86868b]">{when(u.created_at)}</span>
              </div>
              <p className={`mt-1 font-medium leading-snug text-[#1d1d1f] ${compact ? "line-clamp-2 text-sm" : "text-[15px]"}`}>
                {u.title.replace(/^Advertisement dated [^:]+:\s*/i, "")}
              </p>
              {!compact && u.detail && (
                <p className="mt-1 line-clamp-2 whitespace-pre-line text-sm text-[#6e6e73]">
                  {u.faculty_name ? `Prof. ${u.faculty_name} · ` : ""}
                  {u.detail}
                </p>
              )}
            </Row>
          </li>
        );
      })}
    </ul>
  );
}
