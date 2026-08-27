import React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "./Button";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: { value: string; label: string }[];
  label?: string;
  error?: string;
  /**
   * Inline mode: renders just the select (no full-width wrapper, no label column)
   * so it can sit inside filter bars, table cells and pagination rows.
   * Pass a width via className (e.g. `w-auto`, `flex-1`).
   */
  inline?: boolean;
}

const selectBase =
  "appearance-none bg-app-bg border rounded-lg pl-3.5 pr-9 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none transition cursor-pointer";

/** Token-styled select with label + error, consistent with TextInput & NumberInput. */
export const Select: React.FC<SelectProps> = ({
  options,
  label,
  error,
  inline = false,
  className,
  ...props
}) => {
  const field = cn(
    selectBase,
    "w-full",
    error ? "border-status-critical focus:border-status-critical" : "border-line-subtle focus:border-accent-primary",
    className
  );

  const select = (
    <div className="relative">
      <select className={field} {...props}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={14}
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-content-tertiary"
      />
    </div>
  );

  if (inline) return select;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label htmlFor={props.id || props.name} className="text-xs font-semibold text-content-secondary">
          {label}
        </label>
      )}
      {select}
      {error && <span className="text-xs text-status-critical mt-0.5">{error}</span>}
    </div>
  );
};

export default Select;
