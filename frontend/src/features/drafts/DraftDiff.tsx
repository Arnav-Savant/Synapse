/** A unified diff against the file on disk: what the merge would add and remove. */
export function DraftDiff({ diff }: { diff: string }) {
  if (!diff.trim()) {
    return <p className="text-sm text-muted">The draft is identical to the note on disk.</p>;
  }
  return (
    <pre className="overflow-x-auto rounded-control border border-line bg-sunken py-2 font-mono text-[12.5px] leading-relaxed" aria-label="Changes to the existing note">
      {diff.split("\n").map((line, i) => {
        const style = line.startsWith("+") && !line.startsWith("+++")
          ? "bg-ok-soft text-ok"
          : line.startsWith("-") && !line.startsWith("---")
            ? "bg-danger-soft text-danger"
            : line.startsWith("@@")
              ? "text-info"
              : "text-muted";
        return (
          <div key={i} className={`whitespace-pre-wrap break-words px-4 ${style}`}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
