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
 * NOCTRA mark — SIGNAL identity (design source: newfile.html).
 *
 * Icon: the signal-dot — a small green transmission dot with a soft halo
 * and a slow pulse (live monitoring). It is the same dot that marks
 * "systems nominal" across the console.
 * Wordmark: "NOCTRA" in DM Sans Bold, uppercase, wide tracking
 * (0.22em — matches the Canva header lockup). No divider, no gradient.
 */
const BrandLogo: React.FC<Props> = ({
  collapsed = false,
  size = 28,
  withWordmark = true,
  mono = false,
  className,
}) => {
  const dotSize = Math.max(8, Math.round(size * 0.3));
  const dotColor = mono ? "currentColor" : "#a6ff3f";

  const icon = (
    <span
      className={mono ? "inline-flex items-center shrink-0" : "inline-flex items-center shrink-0"}
      style={{ width: dotSize + 10, height: dotSize + 10, justifyContent: "center" }}
      aria-hidden
    >
      <span
        className={mono ? "" : "signal-dot"}
        style={{
          width: dotSize,
          height: dotSize,
          borderRadius: 999,
          background: dotColor,
          boxShadow: mono
            ? undefined
            : "0 0 0 4px rgba(166,255,63,.12), 0 0 14px rgba(166,255,63,.8)",
        }}
      />
    </span>
  );

  if (!withWordmark || collapsed) {
    return <span className={`inline-flex items-center ${className || ""}`}>{icon}</span>;
  }

  return (
    <span className={`inline-flex items-center gap-3 ${className || ""}`}>
      {icon}
      <span className="flex flex-col leading-none">
        <span
          className="text-[15px] font-bold font-display tracking-[0.22em] uppercase text-content-primary"
          style={{ fontSize: Math.max(13, size * 0.56) }}
        >
          NOCTRA
        </span>
        {!mono && size >= 40 && (
          <span className="tech-label text-content-tertiary mt-1.5 whitespace-nowrap">
            Threat intelligence, always on
          </span>
        )}
      </span>
    </span>
  );
};

export default BrandLogo;
