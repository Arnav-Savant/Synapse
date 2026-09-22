import type { FilterOptions } from "./filters";

interface FilterControlsProps {
  domainOptions: string[];
  statusOptions: string[];
  filters: FilterOptions;
  onChange: (filters: FilterOptions) => void;
}

export function FilterControls({ domainOptions, statusOptions, filters, onChange }: FilterControlsProps) {
  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  return (
    <div className="flex flex-wrap items-center gap-4 text-sm">
      <FilterGroup
        label="Domain"
        options={domainOptions}
        selected={filters.domains}
        onToggle={(value) => onChange({ ...filters, domains: toggle(filters.domains, value) })}
      />
      <FilterGroup
        label="Status"
        options={statusOptions}
        selected={filters.statuses}
        onToggle={(value) => onChange({ ...filters, statuses: toggle(filters.statuses, value) })}
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
      <span className="text-slate-500">{label}:</span>
      {options.map((option) => (
        <button
          key={option}
          onClick={() => onToggle(option)}
          className={`rounded-full border px-2 py-0.5 text-xs ${
            selected.includes(option)
              ? "border-slate-800 bg-slate-800 text-white"
              : "border-slate-300 text-slate-600 hover:bg-slate-50"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
