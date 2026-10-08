/**
 * VectorShield — Animated SVG cybersecurity shield icon.
 *
 * A hand-drawn vector shield with pulsing glow, circuit lines,
 * and an animated lock/check emblem. Used as a branding element
 * and status indicator throughout the dashboard.
 */
interface VectorShieldProps {
  size?: number;
  status?: 'secure' | 'warning' | 'breach';
  animate?: boolean;
  className?: string;
}

const STATUS_COLORS = {
  secure: { primary: '#05ffa1', glow: 'rgba(5, 255, 161, 0.6)' },
  warning: { primary: '#fcee0a', glow: 'rgba(252, 238, 10, 0.6)' },
  breach: { primary: '#ff2a6d', glow: 'rgba(255, 42, 109, 0.6)' },
};

export function VectorShield({
  size = 64,
  status = 'secure',
  animate = true,
  className = '',
}: VectorShieldProps) {
  const colors = STATUS_COLORS[status];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      role="img"
      aria-label={`Security status: ${status}`}
    >
      <defs>
        <filter id={`shieldGlow-${status}`}>
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <linearGradient id={`shieldGrad-${status}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={colors.primary} stopOpacity="0.8" />
          <stop offset="100%" stopColor={colors.primary} stopOpacity="0.3" />
        </linearGradient>
      </defs>

      {/* Shield outline */}
      <path
        d="M32 4 L52 14 L52 30 C52 42 42 52 32 58 C22 52 12 42 12 30 L12 14 Z"
        fill="none"
        stroke={colors.primary}
        strokeWidth="2"
        filter={animate ? `url(#shieldGlow-${status})` : undefined}
      >
        {animate && (
          <animate
            attributeName="stroke-opacity"
            values="1;0.5;1"
            dur="2s"
            repeatCount="indefinite"
          />
        )}
      </path>

      {/* Shield fill gradient */}
      <path
        d="M32 6 L50 15 L50 30 C50 41 41 50 32 56 C23 50 14 41 14 30 L14 15 Z"
        fill={`url(#shieldGrad-${status})`}
        opacity="0.15"
      />

      {/* Circuit lines inside shield */}
      <path
        d="M24 22 L32 22 L32 30 L40 30"
        fill="none"
        stroke={colors.primary}
        strokeWidth="1"
        opacity="0.5"
        strokeDasharray="2 2"
      >
        {animate && (
          <animate
            attributeName="stroke-dashoffset"
            from="0"
            to="8"
            dur="1s"
            repeatCount="indefinite"
          />
        )}
      </path>
      <path
        d="M28 38 L32 38 L32 30"
        fill="none"
        stroke={colors.primary}
        strokeWidth="1"
        opacity="0.5"
        strokeDasharray="2 2"
      />

      {/* Center emblem */}
      {status === 'secure' ? (
        <g filter={animate ? `url(#shieldGlow-${status})` : undefined}>
          {/* Checkmark */}
          <path
            d="M25 32 L30 37 L39 27"
            fill="none"
            stroke={colors.primary}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {animate && (
              <animate
                attributeName="stroke-dasharray"
                from="0 100"
                to="30 100"
                dur="0.5s"
                fill="freeze"
              />
            )}
          </path>
        </g>
      ) : status === 'warning' ? (
        <g filter={animate ? `url(#shieldGlow-${status})` : undefined}>
          <text
            x="32"
            y="38"
            textAnchor="middle"
            fill={colors.primary}
            fontSize="18"
            fontWeight="bold"
            fontFamily="monospace"
          >
            !
          </text>
        </g>
      ) : (
        <g filter={animate ? `url(#shieldGlow-${status})` : undefined}>
          <path
            d="M26 26 L38 38 M38 26 L26 38"
            fill="none"
            stroke={colors.primary}
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </g>
      )}

      {/* Pulse ring */}
      {animate && (
        <circle cx="32" cy="32" r="30" fill="none" stroke={colors.primary} strokeWidth="0.5">
          <animate attributeName="r" from="28" to="34" dur="2s" repeatCount="indefinite" />
          <animate attributeName="opacity" from="0.4" to="0" dur="2s" repeatCount="indefinite" />
        </circle>
      )}
    </svg>
  );
}