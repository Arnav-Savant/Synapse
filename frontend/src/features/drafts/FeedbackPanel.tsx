import { Card } from "../../design/Card";
import { Field, SelectInput, TextArea } from "../../design/Field";
import type { FeedbackForm } from "./draftDecision";

interface FeedbackPanelProps {
  form: FeedbackForm;
  onChange: (form: FeedbackForm) => void;
  sections: string[];
  noteTitle: string;
}

const SCOPES: { value: FeedbackForm["scope"]; label: string }[] = [
  { value: "section", label: "One section of this note" },
  { value: "note", label: "This whole note" },
  { value: "topic", label: "The whole topic, every note" },
];

/** Feedback regenerates only what is named, in place, and the drafts come back here for another look. */
export function FeedbackPanel({ form, onChange, sections, noteTitle }: FeedbackPanelProps) {
  const set = (patch: Partial<FeedbackForm>) => onChange({ ...form, ...patch });
  return (
    <Card>
      <h3 className="mb-4 font-semibold">Ask for changes to “{noteTitle}”</h3>
      <div className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="What should change?">
            {(c) => (
              <SelectInput {...c} value={form.scope} onChange={(e) => set({ scope: e.target.value as FeedbackForm["scope"] })}>
                {SCOPES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </SelectInput>
            )}
          </Field>
          {form.scope === "section" ? (
            <Field label="Section">
              {(c) => (
                <SelectInput {...c} value={form.section} onChange={(e) => set({ section: e.target.value })}>
                  <option value="">Choose a section</option>
                  {sections.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </SelectInput>
              )}
            </Field>
          ) : null}
        </div>
        <Field label="Feedback" hint="Be specific: what is wrong or missing, and what you would rather see.">
          {(c) => <TextArea {...c} rows={3} value={form.text} onChange={(e) => set({ text: e.target.value })} />}
        </Field>
        <label className="flex items-start gap-2.5 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 accent-[var(--accent)]"
            checked={form.reResearch}
            onChange={(e) => set({ reResearch: e.target.checked })}
          />
          <span>
            Research again before rewriting
            <span className="block text-muted">Only needed when the facts are wrong or thin. It costs more and takes longer.</span>
          </span>
        </label>
      </div>
    </Card>
  );
}
