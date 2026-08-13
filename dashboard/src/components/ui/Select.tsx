import React from "react";
import { cn } from "./Button";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: { value: string; label: string }[];
  label?: string;
  error?: string;
}

/** Token-styled select with label + error, consistent with TextInput. */
export const Select: React.FC<SelectProps> = ({
  options,
  label,
  error,
  className,
  ...props
}) => (
  <div className="flex flex-col gap-1.5 w-full">
    {label && (
      <label htmlFor={props.id || props.name} className="text-xs font-semibold text-content-secondary">
        {label}
      </label>
    )}
    <select
      className={cn(
        "bg-app-bg border rounded-lg px-3.5 py-2 text-sm text-content-primary focus:outline-none transition cursor-pointer",
        error ? "border-red-500 focus:border-red-500" : "border-line-subtle focus:border-accent-primary",
        className
      )}
      {...props}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
    {error && <span className="text-xs text-red-400 mt-0.5">{error}</span>}
  </div>
);