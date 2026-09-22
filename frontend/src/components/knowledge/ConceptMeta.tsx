import type { KnowledgeDetail } from "../../api/knowledge";
import { colorForDomains } from "../graph/domainColors";

interface ConceptMetaProps {
  detail: KnowledgeDetail;
  onNavigate: (slug: string) => void;
}

export function ConceptMeta({ detail, onNavigate }: ConceptMetaProps) {
  return (
    <div className="space-y-3 border-b border-paper-line pb-5">
      <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
        <span className="border border-paper-ink/25 px-1.5 py-0.5 text-paper-ink/50">{detail.status}</span>
        {detail.domains.map((domain) => (
          <span
            key={domain}
            className="border px-1.5 py-0.5"
            style={{ borderColor: colorForDomains([domain]), color: colorForDomains([domain]) }}
          >
            {domain}
          </span>
        ))}
      </div>

      <h2 className="font-serif text-3xl leading-tight text-paper-ink">{detail.title}</h2>

      {detail.aliases.length > 0 && (
        <p className="font-mono text-[11px] text-paper-ink/40">also known as {detail.aliases.join(", ")}</p>
      )}

      {detail.relationships.length > 0 && (
        <ul className="space-y-0.5 pt-1 font-mono text-[11px] text-paper-ink/60">
          {detail.relationships.map((rel, index) => (
            <li key={index}>
              {rel.type}{" "}
              <button onClick={() => onNavigate(rel.target)} className="text-spark-dim hover:text-paper-ink">
                {rel.target}
              </button>
              {rel.note && <span className="text-paper-ink/40"> — {rel.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
