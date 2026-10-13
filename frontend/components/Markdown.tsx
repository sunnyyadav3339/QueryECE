import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function Markdown({ children }: { children: string }) {
  return (
    <div className="prose-chat text-[15px] leading-relaxed text-slate-700">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {children
          // gpt-oss sometimes cites as 【1】 / 【1†source】 while streaming.
          .replace(/【(\d+)[^】]*】/g, "[$1]")
          // Raw HTML isn't rendered; models use <br> inside table cells.
          .replace(/<br\s*\/?>/gi, " ")}
      </ReactMarkdown>
    </div>
  );
}
