import React, { useRef } from "react";
import { Minus, Plus } from "lucide-react";
import { cn } from "./Button";

/**
 * NumberInput — a consistent number stepper (spinner / spin-button / up-down
 * control). Replaces the browser-native `type="number"` spinners, which look
 * different in every browser. Minus/Plus buttons on both sides, a centered
 * value, full keyboard support, and the same field styling as TextInput/Select.
 *
 * Usage mirrors <input type="number">:
 *   controlled:  <NumberInput min={1} max={100} value={n} onChange={(v) => setN(v)} />
 *   uncontrolled:<NumberInput min={0} max={1} step={0.05} defaultValue={0.7} onChange={...} />
 * `onChange` receives the parsed number (or NaN for an empty field).
 */
export interface NumberInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value" | "type"> {
  value?: number | string;
  defaultValue?: number | string;
  onChange?: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label?: string;
  error?: string;
  /** Extra classes for the inner text field (e.g. `font-mono`, `text-xs`). */
  fieldClassName?: string;
}

export const NumberInput: React.FC<NumberInputProps> = ({
  value,
  defaultValue,
  onChange,
  min = -Infinity,
  max = Infinity,
  step = 1,
  label,
  error,
  className,
  fieldClassName,
  id,
  name,
  placeholder,
  disabled,
  ...props
}) => {
  const inputRef = useRef<HTMLInputElement>(null);

  const clamp = (n: number): number => {
    if (Number.isNaN(n)) return n;
    return Math.min(max, Math.max(min, n));
  };

  /** Read the live field value — works for both controlled and uncontrolled. */
  const currentValue = (): number => {
    const raw = inputRef.current?.value ?? "";
    return raw === "" ? NaN : Number(raw);
  };

  const commit = (next: number) => {
    const clamped = clamp(next);
    if (inputRef.current) inputRef.current.value = String(clamped);
    onChange?.(clamped);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const base = currentValue();
      commit((Number.isNaN(base) ? (defaultValue ? Number(defaultValue) || 0 : 0) : base) + step);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const base = currentValue();
      commit((Number.isNaN(base) ? (defaultValue ? Number(defaultValue) || 0 : 0) : base) - step);
    }
    props.onKeyDown?.(e);
  };

  const baseField =
    "w-full bg-app-bg border rounded-lg px-3.5 py-2 text-sm text-content-primary placeholder-content-tertiary focus:outline-none transition";

  const field = cn(
    baseField,
    error ? "border-status-critical focus:border-status-critical" : "border-line-subtle focus:border-accent-primary",
    disabled && "opacity-50 cursor-not-allowed"
  );

  const stepBtn = cn(
    "w-9 shrink-0 flex items-center justify-center border text-content-secondary hover:text-content-primary hover:bg-app-subtle transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed",
    error ? "border-status-critical/50" : "border-line-subtle"
  );

  const numericValue = value !== undefined ? Number(value) : undefined;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label htmlFor={id || name} className="text-xs font-semibold text-content-secondary">
          {label}
        </label>
      )}
      <div className={cn("flex items-stretch rounded-lg", className)}>
        <button
          type="button"
          tabIndex={-1}
          aria-label="Decrease"
          onClick={() => commit((Number.isNaN(currentValue()) ? (defaultValue ? Number(defaultValue) || 0 : 0) : currentValue()) - step)}
          disabled={disabled || (numericValue !== undefined && !Number.isNaN(numericValue) && numericValue <= min)}
          className={cn(stepBtn, "rounded-l-lg border-r-0")}
        >
          <Minus size={13} aria-hidden />
        </button>
        <input
          ref={inputRef}
          id={id}
          name={name}
          type="text"
          inputMode="decimal"
          pattern="[0-9.]*"
          value={value !== undefined ? String(value) : undefined}
          defaultValue={value !== undefined ? undefined : defaultValue}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(e) => onChange?.(e.target.value === "" ? NaN : Number(e.target.value))}
          onKeyDown={handleKeyDown}
          className={cn(field, "rounded-none text-center tabular-nums", fieldClassName)}
          {...props}
        />
        <button
          type="button"
          tabIndex={-1}
          aria-label="Increase"
          onClick={() => commit((Number.isNaN(currentValue()) ? (defaultValue ? Number(defaultValue) || 0 : 0) : currentValue()) + step)}
          disabled={disabled || (numericValue !== undefined && !Number.isNaN(numericValue) && numericValue >= max)}
          className={cn(stepBtn, "rounded-r-lg border-l-0")}
        >
          <Plus size={13} aria-hidden />
        </button>
      </div>
      {error && <span className="text-xs text-status-critical mt-0.5">{error}</span>}
    </div>
  );
};

export default NumberInput;
