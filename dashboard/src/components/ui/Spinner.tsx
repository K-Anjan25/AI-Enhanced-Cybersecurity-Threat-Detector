/**
 * Spinner — the visual half of a loading control (design.md §8.1: "Spinners only
 * for actions under 1 s").
 *
 * Decorative by construction: rotation carries no information, and the *state* is
 * announced by the control that owns it — `Button` sets `aria-busy` and keeps its
 * name, `Card` renders a labelled skeleton region. A spinner that announced itself
 * would say "loading" twice.
 *
 * Lucide, at the 16 px icon token (design.md §5.6), and `animate-spin` is
 * suppressed by the global `prefers-reduced-motion` rule in index.css — motion
 * here is continuity, not decoration (§8.2).
 */
import { Loader2 } from 'lucide-react';

export function Spinner() {
  return (
    <span aria-hidden="true" className="inline-flex animate-spin text-current">
      <Loader2 className="size-icon-sm" />
    </span>
  );
}
