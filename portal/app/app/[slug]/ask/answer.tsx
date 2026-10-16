"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders the assistant's Markdown (bold, lists, tables, links) in the portal's plain style.
// Links open in a new tab; raw HTML in the answer is not rendered.
export function Answer({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: (props) => <p className="my-2 first:mt-0 last:mb-0" {...props} />,
        ul: (props) => <ul className="my-2 list-disc space-y-1 pl-5" {...props} />,
        ol: (props) => <ol className="my-2 list-decimal space-y-1 pl-5" {...props} />,
        strong: (props) => <strong className="font-semibold" {...props} />,
        a: (props) => <a className="underline underline-offset-2" target="_blank" rel="noreferrer noopener" {...props} />,
        h1: (props) => <p className="mb-1 mt-3 font-semibold" {...props} />,
        h2: (props) => <p className="mb-1 mt-3 font-semibold" {...props} />,
        h3: (props) => <p className="mb-1 mt-3 font-semibold" {...props} />,
        code: (props) => <code className="rounded bg-genie-accent px-1 font-mono text-[0.9em]" {...props} />,
        table: (props) => (
          <div className="my-2 overflow-x-auto">
            <table className="w-full border-collapse text-left" {...props} />
          </div>
        ),
        th: (props) => <th className="border-b border-genie-border px-2 py-1 font-medium text-genie-muted" {...props} />,
        td: (props) => <td className="border-b border-genie-border px-2 py-1 align-top" {...props} />,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
