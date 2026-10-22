import { PATHS, type SocialName } from './socialPaths';

/**
 * Brand glyphs from Simple Icons (CC0-1.0). Lucide dropped brand marks in v1, so they
 * are inlined as single-path SVGs drawn in the current text colour.
 */
export function SocialIcon({
  name,
  className = 'size-icon-md',
}: {
  name: SocialName;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={`fill-current ${className}`}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
