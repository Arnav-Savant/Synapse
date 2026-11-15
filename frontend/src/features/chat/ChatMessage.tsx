import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatMessage as Message } from "../../api/chats";
import { Chip } from "../../design/Chip";
import { Spinner } from "../../design/Spinner";
import { formatCost } from "../jobs/jobStatus";
import { citedInOrder, linkCitations } from "./chatText";

/** Citation links point at the Sources list below the answer; they never leave the app. */
function AnswerLink({ href, children, ...rest }: ComponentProps<"a">) {
  if (href?.startsWith("#cite-")) {
    return (
      <sup className="mx-px rounded bg-accent-soft px-1 text-[11px] font-semibold text-accent" title="See Sources below">
        {children}
      </sup>
    );
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" {...rest}>
      {children}
    </a>
  );
}

/** A wide table scrolls inside the answer instead of widening the page. */
function AnswerTable({ children }: ComponentProps<"table">) {
  return (
    <div className="overflow-x-auto">
      <table>{children}</table>
    </div>
  );
}

function Cost({ usd }: { usd: number }) {
  return usd > 0 ? <p className="mt-2 text-xs text-faint">{formatCost(usd)}</p> : null;
}

function Answer({ message }: { message: Message }) {
  const sources = citedInOrder(message.text, message.citations);
  return (
    <>
      <article className="prose prose-note max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: AnswerLink, table: AnswerTable }} urlTransform={(url) => url}>
          {linkCitations(message.text, message.citations)}
        </ReactMarkdown>
      </article>
      {sources.length > 0 ? (
        <section className="mt-4" aria-label="Sources">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Sources</h3>
          <ol className="flex flex-col gap-0.5 text-sm text-muted">
            {sources.map((c, index) => (
              <li key={c.ref}>
                {index + 1}. <span className="text-fg">{c.title}</span>
                {c.heading ? ` › ${c.heading}` : ""} ({c.domain})
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      {message.gaps.length > 0 ? (
        <section className="mt-4" aria-label="Not in your notes">
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Not in your notes</h3>
          <div className="flex flex-wrap gap-1.5">
            {message.gaps.map((gap) => (
              <Chip key={gap} tone="warn">
                {gap}
              </Chip>
            ))}
          </div>
        </section>
      ) : null}
      {message.flags.length > 0 ? (
        <div className="mt-4 rounded-control bg-warn-soft p-3 text-sm text-warn" role="note">
          <p className="font-medium">The checker was not fully satisfied with this answer:</p>
          <ul className="mt-1 list-disc pl-5">
            {message.flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

export function ChatMessage({ message }: { message: Message }) {
  if (message.role === "owner") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-panel bg-accent-soft px-4 py-2.5 text-fg">{message.text}</p>
      </div>
    );
  }

  const body =
    message.status === "pending" ? (
      <p className="flex items-center gap-2.5 text-muted" role="status">
        <Spinner label="Working" />
        <span>{message.step ?? "Thinking"}</span>
      </p>
    ) : message.status === "failed" ? (
      <p className="text-danger" role="alert">
        {message.error ?? "This answer failed."}
      </p>
    ) : message.kind === "question" ? (
      <>
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-info">A question for you</p>
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
      </>
    ) : (
      <Answer message={message} />
    );

  const tone =
    message.status === "failed"
      ? "border-danger/50 bg-danger-soft"
      : message.kind === "question" && message.status === "answered"
        ? "border-info/40 bg-info-soft"
        : "border-line bg-surface";

  return (
    <div className="flex">
      <div className={`min-w-0 max-w-full rounded-panel border px-4 py-3.5 md:max-w-[92%] ${tone}`}>
        {body}
        {message.status === "answered" || message.status === "failed" ? <Cost usd={message.cost_usd} /> : null}
      </div>
    </div>
  );
}
