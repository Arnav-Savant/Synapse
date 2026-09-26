import type { FilterOptions } from "./filters";

interface FilterControlsProps {
  categoryOptions: string[];
  filters: FilterOptions;
  onChange: (filters: FilterOptions) => void;
}

export function FilterControls({ categoryOptions, filters, onChange }: FilterControlsProps) {
  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  return (
    <div className="flex flex-wrap items-center gap-4">
      <FilterGroup
        label="category"
        options={categoryOptions}
        selected={filters.categories}
        onToggle={(value) => onChange({ ...filters, categories: toggle(filters.categories, value) })}
      />
    </div>
  );
}

function FilterGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  if (options.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-graphite">{label}:</span>
      {options.map((option) => (
        <button
          key={option}
          onClick={() => onToggle(option)}
          className={`rounded-sm border px-2 py-0.5 ${
            selected.includes(option)
              ? "border-spark text-spark"
              : "border-ink-line text-graphite hover:border-graphite hover:text-paper"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
