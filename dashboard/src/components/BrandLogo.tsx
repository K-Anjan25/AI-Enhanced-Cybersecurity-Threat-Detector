import React, { useId } from "react";

type Props = {
  collapsed?: boolean;
  size?: number;
  withWordmark?: boolean;
  /** Monochrome variant — everything currentColor (for non-brand surfaces). */
  mono?: boolean;
  className?: string;
};

/**
 * NOCTRA mark — crescent moon brand mark (2026-08-27, per design review).
 *
 * Icon: a crescent moon (night watch) in a diagonal violet gradient
 * #6C5CE7 → #9D7CFF (top-left dark → bottom-right light). A 4-pointed
 * sparkle (#B18CFF) — insight — sits at the crescent's upper tip.
 * Wordmark: "NOCTRA" in Sora SemiBold, uppercase, slightly extended
 * tracking; the "A" carries a sparkle at its apex. Tagline beneath in Inter
 * Medium, wide tracking, #9D7CFF. Lockup: [icon] [divider] [wordmark+tagline].
 */
const BrandLogo: React.FC<Props> = ({
  collapsed = false,
  size = 28,
  withWordmark = true,
  mono = false,
  className,
}) => {
  const uid = useId().replace(/[:]/g, "");
  const gradId = `noctra-moon-${uid}-${mono ? "mono" : "color"}`;
  const maskId = `noctra-moon-${uid}-cut`;
  const fillMain = mono ? "currentColor" : `url(#${gradId})`;
  const sparkleFill = mono ? "currentColor" : "#B18CFF";

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
        <mask id={maskId}>
          <rect width="32" height="32" fill="white" />
          {/* Bite cut — removes the upper-right disc to form the crescent. */}
          <circle cx="21" cy="11" r="9" fill="black" />
        </mask>
      </defs>

      {/* Crescent moon — full disc in the brand gradient, bite cut via mask. */}
      <circle cx="16" cy="16" r="12" fill={fillMain} mask={`url(#${maskId})`} />
      {/* Insight sparkle at the crescent's upper tip. */}
      <path
        d="M6 0 C6.6 2.9 9.1 5.4 12 6 C9.1 6.6 6.6 9.1 6 12 C5.4 9.1 2.9 6.6 0 6 C2.9 5.4 5.4 2.9 6 0 Z"
        transform="translate(23.8 1.4) scale(0.42)"
        fill={sparkleFill}
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
