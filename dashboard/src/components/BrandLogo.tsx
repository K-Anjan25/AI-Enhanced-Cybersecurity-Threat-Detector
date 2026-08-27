import React from "react";

type Props = {
  collapsed?: boolean;
  size?: number;
  withWordmark?: boolean;
  /** Monochrome variant — everything currentColor (for non-brand surfaces). */
  mono?: boolean;
  className?: string;
};

/**
 * NOCTRA mark — exact brand specification (2026-08-27).
 *
 * Icon: a bold geometric "N" built as a folded ribbon (blade/origami zigzag)
 * with faceted overlays, in a diagonal purple gradient #6C5CE7 → #9D7CFF
 * (top-left dark → bottom-right light). A 4-pointed sparkle (#B18CFF) —
 * insight — sits at the N's top-right corner.
 * Wordmark: "NOCTRA" in Sora SemiBold, uppercase, slightly extended
 * tracking; the "A" carries a sparkle at its apex. Tagline beneath in Inter
 * Medium, wide tracking, #9D7CFF. Lockup: [icon] [divider] [wordmark+tagline].
 * Clear space: one star-icon height on all sides.
 */
const BrandLogo: React.FC<Props> = ({
  collapsed = false,
  size = 28,
  withWordmark = true,
  mono = false,
  className,
}) => {
  const gradId = `noctra-n-${mono ? "mono" : "color"}`;
  const fillMain = mono ? "currentColor" : `url(#${gradId})`;

  const icon = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      className="shrink-0"
    >
      <defs>
        <linearGradient id={gradId} x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={mono ? "currentColor" : "#6C5CE7"} />
          <stop offset="1" stopColor={mono ? "currentColor" : "#9D7CFF"} />
        </linearGradient>
      </defs>

      {/* Folded-ribbon N: left bar → diagonal → right bar, one continuous path. */}
      <path
        d="M7 26 V6 H13.5 L21.5 16.8 V6 H28 V26 H21.5 L13.5 15.2 V26 Z"
        fill={fillMain}
      />
      {/* Facets — a fold line through the diagonal band (subtle, flat vector). */}
      <path
        d="M13.5 6 L21.5 16.8 L21.5 21.4 L13.5 10.6 Z"
        fill={mono ? "none" : "#FFFFFF"}
        fillOpacity={mono ? 0 : 0.10}
      />
      <path
        d="M13.5 15.2 L21.5 26 L21.5 21.4 L13.5 10.6 Z"
        fill={mono ? "none" : "#FFFFFF"}
        fillOpacity={mono ? 0 : 0.05}
      />
      {/* Insight sparkle at the N's top-right corner. */}
      <path
        d="M28 1.2 C28.5 3.5 30.5 5.5 32.8 6 C30.5 6.5 28.5 8.5 28 10.8 C27.5 8.5 25.5 6.5 23.2 6 C25.5 5.5 27.5 3.5 28 1.2 Z"
        transform="translate(-1.2 0) scale(0.94)"
        fill={mono ? "currentColor" : "#B18CFF"}
      />
    </svg>
  );

  if (!withWordmark || collapsed) {
    return <span className={`inline-flex items-center ${className || ""}`}>{icon}</span>;
  }

  return (
    <span className={`inline-flex items-center gap-3 ${className || ""}`}>
      {icon}
      {/* Thin vertical divider per lockup spec. */}
      <span className="w-px h-[26px] bg-line-bright" aria-hidden />
      <span className="flex flex-col leading-none">
        <span className="flex items-center text-[15px] font-semibold font-display tracking-[0.07em] uppercase text-content-primary">
          {"NOCTR"}
          {/* Stylized A — sparkle at its apex (intelligence/autonomy). */}
          <span className="relative inline-block">
            A
            <svg
              width="8"
              height="8"
              viewBox="0 0 12 12"
              className="absolute -top-1 -right-1.5"
              aria-hidden
            >
              <path
                d="M6 0 C6.6 2.9 9.1 5.4 12 6 C9.1 6.6 6.6 9.1 6 12 C5.4 9.1 2.9 6.6 0 6 C2.9 5.4 5.4 2.9 6 0 Z"
                fill="#B18CFF"
              />
            </svg>
          </span>
        </span>
        <span className="text-[7px] font-medium font-sans tracking-[0.18em] text-[#9d7cff] uppercase mt-1.5 whitespace-nowrap">
          Your autonomous security analyst
        </span>
      </span>
    </span>
  );
};

export default BrandLogo;
