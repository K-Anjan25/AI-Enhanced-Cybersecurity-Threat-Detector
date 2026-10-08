/**
 * PerformanceContext — Global toggle for heavy cyberpunk effects.
 *
 * Provides a "performance mode" that disables expensive animations
 * (MatrixRain, DataStream, continuous PulseWave, radar sweep) to
 * reduce RAM/CPU usage. Stored in localStorage for persistence.
 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';

interface PerformanceState {
  /** When true, heavy animations are disabled */
  performanceMode: boolean;
  /** When true, the 3D globe is rendered (biggest RAM consumer) */
  showGlobe: boolean;
  /** When true, the matrix rain canvas is rendered */
  showMatrixRain: boolean;
  /** When true, continuous pulse/radar animations run */
  showAnimations: boolean;
  /** Toggle performance mode on/off */
  togglePerformanceMode: () => void;
  /** Toggle globe visibility */
  toggleGlobe: () => void;
  /** Toggle matrix rain */
  toggleMatrixRain: () => void;
}

const PerformanceContext = createContext<PerformanceState | null>(null);

const STORAGE_KEY = 'aegis-performance-mode';

export function PerformanceProvider({ children }: { children: ReactNode }) {
  const [performanceMode, setPerformanceMode] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const [showGlobe, setShowGlobe] = useState(() => {
    try {
      const stored = localStorage.getItem('aegis-show-globe');
      return stored !== 'false'; // default true
    } catch {
      return true;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(performanceMode));
    } catch {
      // localStorage unavailable
    }
  }, [performanceMode]);

  useEffect(() => {
    try {
      localStorage.setItem('aegis-show-globe', String(showGlobe));
    } catch {
      // localStorage unavailable
    }
  }, [showGlobe]);

  const togglePerformanceMode = useCallback(() => {
    setPerformanceMode((prev) => !prev);
  }, []);

  const toggleGlobe = useCallback(() => {
    setShowGlobe((prev) => !prev);
  }, []);

  return (
    <PerformanceContext.Provider
      value={{
        performanceMode,
        showGlobe,
        showMatrixRain: !performanceMode,
        showAnimations: !performanceMode,
        togglePerformanceMode,
        toggleGlobe,
        toggleMatrixRain: () => {},
      }}
    >
      {children}
    </PerformanceContext.Provider>
  );
}

export function usePerformance(): PerformanceState {
  const ctx = useContext(PerformanceContext);
  if (!ctx) throw new Error('usePerformance must be used within PerformanceProvider');
  return ctx;
}