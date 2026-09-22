import type { KnowledgeDetail } from "../../api/knowledge";

const STATUS_COLORS: Record<string, string> = {
  stub: "bg-slate-100 text-slate-600",
  developing: "bg-amber-100 text-amber-700",
  stable: "bg-emerald-100 text-emerald-700",
};

interface ConceptMetaProps {
  detail: KnowledgeDetail;
  onNavigate: (slug: string) => void;
}

export function ConceptMeta({ detail, onNavigate }: ConceptMetaProps) {
  return (
    <div className="space-y-2 border-b border-slate-200 pb-3">
      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold text-slate-800">{detail.title}</h2>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[detail.status] ?? STATUS_COLORS.stub}`}>
          {detail.status}
        </span>
      </div>

      {detail.aliases.length > 0 && (
        <p className="text-xs text-slate-500">aka {detail.aliases.join(", ")}</p>
      )}

      {detail.domains.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {detail.domains.map((domain) => (
            <span key={domain} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
              {domain}
            </span>
          ))}
        </div>
      )}

      {detail.relationships.length > 0 && (
        <ul className="space-y-0.5 text-xs text-slate-600">
          {detail.relationships.map((rel, index) => (
            <li key={index}>
              <span className="text-slate-400">{rel.type}</span>{" "}
              <button
                onClick={() => onNavigate(rel.target)}
                className="text-sky-700 underline decoration-sky-300 underline-offset-2 hover:text-sky-900"
              >
                {rel.target}
              </button>
              {rel.note && <span className="text-slate-400"> — {rel.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
