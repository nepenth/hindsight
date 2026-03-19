"use client";

import { Checkbox } from "@/components/ui/checkbox";

export type FactType = "world" | "experience" | "observation";

export const ALL_FACT_TYPES: FactType[] = ["world", "experience", "observation"];

/**
 * Inline fact-type checkbox filter. Renders three labelled checkboxes.
 *
 * - In "filter" mode (default) an empty selection means "all types included".
 * - In "select" mode every checked item is explicitly included.
 *
 * The label text for "observation" is "Observations" to match existing UI conventions
 * in the recall view; all others are capitalised from their value.
 */
export function FactTypeFilter({
  value,
  onChange,
  label = "Fact types:",
}: {
  value: FactType[];
  onChange: (next: FactType[]) => void;
  label?: string;
}) {
  const toggle = (ft: FactType) =>
    onChange(value.includes(ft) ? value.filter((f) => f !== ft) : [...value, ft]);

  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-sm font-medium text-muted-foreground">{label}</span>}
      <div className="flex gap-3">
        {ALL_FACT_TYPES.map((ft) => (
          <label key={ft} className="flex items-center gap-1.5 cursor-pointer">
            <Checkbox checked={value.includes(ft)} onCheckedChange={() => toggle(ft)} />
            <span className="text-sm capitalize">{ft === "observation" ? "Observations" : ft}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

/**
 * Vertical variant for use inside forms/dialogs.
 */
export function FactTypeCheckboxGroup({
  value,
  onChange,
}: {
  value: FactType[];
  onChange: (next: FactType[]) => void;
}) {
  const toggle = (ft: FactType) =>
    onChange(value.includes(ft) ? value.filter((f) => f !== ft) : [...value, ft]);

  return (
    <div className="flex flex-wrap gap-3">
      {ALL_FACT_TYPES.map((ft) => (
        <label key={ft} className="flex items-center space-x-1.5 cursor-pointer">
          <Checkbox checked={value.includes(ft)} onCheckedChange={() => toggle(ft)} />
          <span className="text-sm capitalize">{ft}</span>
        </label>
      ))}
    </div>
  );
}
