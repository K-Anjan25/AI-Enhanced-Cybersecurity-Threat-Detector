/**
 * Cyberpunk components — Pure CSS/HTML only, zero JS animation overhead.
 *
 * REMOVED (heavy JS, high RAM):
 *   - MatrixRain (canvas animation loop)
 *   - ThreatRadar (requestAnimationFrame + state updates)
 *   - PulseWave (requestAnimationFrame loop)
 *   - DataStream (setInterval state updates)
 *   - HexGrid (setInterval state updates)
 *   - CyberGlobe (Three.js WebGL)
 *   - PerformanceContext (no longer needed)
 *
 * KEPT (pure HTML/CSS, ~0 KB JS overhead):
 *   - GlitchText (CSS pseudo-elements only)
 *   - NeonCard (CSS + HTML structure)
 *   - CyberButton (CSS only)
 *   - ThreatLevelBar (one-time render, no animation loop)
 *   - VectorShield (static SVG, no animation)
 */
export { GlitchText } from './GlitchText';
export { NeonCard } from './NeonCard';
export { CyberButton } from './CyberButton';
export { ThreatLevelBar } from './ThreatLevelBar';
export { VectorShield } from './VectorShield';