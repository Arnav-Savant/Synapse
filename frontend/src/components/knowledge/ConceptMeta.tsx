import type { KnowledgeDetail } from "../../api/knowledge";
import { colorForCategory } from "../graph/domainColors";

interface ConceptMetaProps {
  detail: KnowledgeDetail;
  onNavigate: (conceptId: string) => void;
}

export function ConceptMeta({ detail, onNavigate }: ConceptMetaProps) {
  return (
    <div className="space-y-3 border-b border-paper-line pb-5">
      <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
        <span
          className="border px-1.5 py-0.5"
          style={{ borderColor: colorForCategory(detail.category), color: colorForCategory(detail.category) }}
        >
          {detail.category}
        </span>
      </div>

      <h2 className="font-serif text-3xl leading-tight text-paper-ink">{detail.title}</h2>

      {detail.relationships.length > 0 && (
        <ul className="space-y-0.5 pt-1 font-mono text-[11px] text-paper-ink/60">
          {detail.relationships.map((rel, index) => {
            // This concept can appear as either endpoint of a stored edge —
            // always navigate to the *other* one, not always the target.
            const otherId = rel.source_id === detail.id ? rel.target_id : rel.source_id;
            return (
              <li key={index}>
                {rel.type}{" "}
                <button onClick={() => onNavigate(otherId)} className="text-spark-dim hover:text-paper-ink">
                  {otherId}
                </button>
                {rel.note && <span className="text-paper-ink/40"> — {rel.note}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
