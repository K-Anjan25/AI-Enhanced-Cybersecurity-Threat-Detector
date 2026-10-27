import logoUrl from '../../assets/aegis-logo.svg';

/**
 * The AEGIS mark. It is drawn as a CSS mask filled with the current text
 * colour, so it follows the theme: white on the dark blue, deep blue on the
 * light one.
 */
export function AegisLogo({ className = 'size-8' }: { className?: string }) {
  const mask = `url(${logoUrl})`;
  return (
    <span
      aria-hidden="true"
      className={`inline-block shrink-0 bg-current ${className}`}
      style={{
        WebkitMaskImage: mask,
        maskImage: mask,
        WebkitMaskRepeat: 'no-repeat',
        maskRepeat: 'no-repeat',
        WebkitMaskPosition: 'center',
        maskPosition: 'center',
        WebkitMaskSize: 'contain',
        maskSize: 'contain',
      }}
    />
  );
}
