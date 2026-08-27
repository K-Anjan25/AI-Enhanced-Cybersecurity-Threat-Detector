import React, { useCallback, useRef, useState } from "react";
import { cn } from "./Button";
import { lookupTerm } from "../../constants/terms";

/**
 * Term — the plain-English annotation primitive (dogfooded terminology).
 *
 * Renders a technical term with a dotted underline; hovering, focusing or
 * tapping opens a small tooltip with the plain-English gloss and the formal
 * technical definition. Keyboard accessible (focusable button + aria-describedby),
 * dismisses on Escape/outside click, honors reduced motion.
 *
 * Usage:
 *   <Term>blast radius</Term>          → lookup from constants/terms.ts
 *   <Term plain="…" formal="…">T1078</Term>  → inline override
 */
export interface TermProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Technical term shown (default: children). If provided, overrides children. */
  term?: string;
  /** Plain-English gloss; falls back to the dictionary entry. */
  plain?: string;
  /** Formal definition; falls back to the dictionary entry. */
  formal?: string;
  /** Render the term in monospace (identifiers, action types, techniques). */
  mono?: boolean;
  /** Prevent tooltip (display-only annotation). */
  inert?: boolean;
}

export function Term({ term, plain, formal, mono = false, inert = false, children, className, ...props }: TermProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const text = term ?? (typeof children === "string" ? children : "");
  const entry = lookupTerm(text);
  const plainText = plain ?? entry?.plain;
  const formalText = formal ?? entry?.formal;

  const close = useCallback(() => setOpen(false), []);

  const toggle = useCallback(() => {
    if (inert || !plainText) return;
    setOpen((v) => !v);
  }, [inert, plainText]);

  if (!plainText) {
    // No gloss available — render as plain text (never a dead tooltip).
    return <span className={cn(mono && "font-mono", className)} {...props}>{children ?? text}</span>;
  }

  return (
    <span className={cn("inline", className)} {...props}>
      <button
        type="button"
        ref={ref as React.RefObject<HTMLButtonElement>}
        onClick={toggle}
        onMouseEnter={() => !inert && setOpen(true)}
        onMouseLeave={close}
        onFocus={() => !inert && setOpen(true)}
        onBlur={(e) => {
          if (!ref.current?.contains(e.relatedTarget as Node)) close();
        }}
        aria-expanded={open}
        aria-describedby={open ? "term-tooltip" : undefined}
        className={cn(
          "inline cursor-help text-left align-baseline underline decoration-dotted underline-offset-[3px] decoration-content-tertiary/70",
          "text-inherit hover:text-accent-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40 focus-visible:rounded-sm",
          mono && "font-mono text-[0.95em]",
          open && "text-accent-secondary"
        )}
      >
        {children ?? text}
      </button>

      {open && (
        <span
          id="term-tooltip"
          role="tooltip"
          className="fixed z-[60] mt-1 w-72 max-w-[85vw] rounded-2xl border border-line-subtle bg-white shadow-float p-3.5 text-left animate-scale-in"
          style={{
            left: Math.min(
              Math.max((ref.current?.getBoundingClientRect().left ?? 0) - 8, 8),
              window.innerWidth - 304
            ),
            top: (ref.current?.getBoundingClientRect().bottom ?? 0) + 6,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-[11px] font-bold uppercase tracking-wider text-content-tertiary">
            {text} — in plain English
          </p>
          <p className="mt-1.5 text-sm font-medium text-content-primary leading-snug">{plainText}</p>
          {formalText && formalText !== plainText && (
            <p className="mt-2 pt-2 border-t border-line-subtle">
              <span className="text-[10px] font-bold uppercase tracking-wider text-content-tertiary">Technical</span>
              <span className="block mt-0.5 text-xs text-content-secondary leading-snug">{formalText}</span>
            </p>
          )}
        </span>
      )}
    </span>
  );
}

export default Term;
