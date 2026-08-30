import React from "react";

/**
 * Collapsed, opt-in view of a raw API payload.
 *
 * Jakob's Law: people arrive expecting the conventions of every other product
 * they use, and no mainstream security console greets an operator with a wall
 * of pretty-printed JSON. These Labs pages did exactly that, which forced the
 * reader to parse a data structure to answer "is anything wrong?".
 *
 * The payload is still one click away — useful while these surfaces are being
 * built out — but it now sits behind a native <details> disclosure, the
 * standard affordance for progressive disclosure, so the summary reads first.
 */
export interface RawDataProps {
  value: unknown;
  label?: string;
  className?: string;
}

export const RawData: React.FC<RawDataProps> = ({ value, label = "Raw response", className }) => {
  if (value === null || value === undefined) return null;

  return (
    <details className={`mt-4 group ${className ?? ""}`}>
      <summary className="cursor-pointer select-none text-[11px] font-mono uppercase tracking-wider text-content-tertiary hover:text-content-secondary transition list-none flex items-center gap-1.5">
        <span className="inline-block transition-transform group-open:rotate-90" aria-hidden>
          ▸
        </span>
        {label}
      </summary>
      <pre className="mt-2 p-4 bg-app-subtle rounded text-xs overflow-auto max-h-[400px] border border-line-subtle text-content-secondary">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
};

export default RawData;
