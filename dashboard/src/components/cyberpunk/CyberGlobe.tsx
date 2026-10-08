/**
 * CyberGlobe — Interactive 3D globe showing network traffic with arcs.
 *
 * Uses react-globe.gl (Three.js-backed) to render a dark-themed earth with
 * animated arcs representing live network traffic / threat origins.
 * The globe auto-rotates and responds to mouse interaction.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import Globe from 'react-globe.gl';

// Major global cities for demo threat arcs
const CITIES = [
  { name: 'New York', lat: 40.7128, lng: -74.006, country: 'US' },
  { name: 'London', lat: 51.5074, lng: -0.1278, country: 'UK' },
  { name: 'Tokyo', lat: 35.6762, lng: 139.6503, country: 'JP' },
  { name: 'Beijing', lat: 39.9042, lng: 116.4074, country: 'CN' },
  { name: 'Moscow', lat: 55.7558, lng: 37.6173, country: 'RU' },
  { name: 'São Paulo', lat: -23.5505, lng: -46.6333, country: 'BR' },
  { name: 'Mumbai', lat: 19.076, lng: 72.8777, country: 'IN' },
  { name: 'Sydney', lat: -33.8688, lng: 151.2093, country: 'AU' },
  { name: 'Berlin', lat: 52.52, lng: 13.405, country: 'DE' },
  { name: 'Seoul', lat: 37.5665, lng: 126.978, country: 'KR' },
  { name: 'Singapore', lat: 1.3521, lng: 103.8198, country: 'SG' },
  { name: 'Dubai', lat: 25.2048, lng: 55.2708, country: 'AE' },
  { name: 'Toronto', lat: 43.6532, lng: -79.3832, country: 'CA' },
  { name: 'Lagos', lat: 6.5244, lng: 3.3792, country: 'NG' },
  { name: 'Buenos Aires', lat: -34.6037, lng: -58.3816, country: 'AR' },
  { name: 'Nairobi', lat: -1.2921, lng: 36.8219, country: 'KE' },
  { name: 'Shanghai', lat: 31.2304, lng: 121.4737, country: 'CN' },
  { name: 'Istanbul', lat: 41.0082, lng: 28.9784, country: 'TR' },
];

interface ArcData {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
  color: string[];
  threatType: string;
}

interface PointData {
  lat: number;
  lng: number;
  size: number;
  color: string;
  name: string;
}

const THREAT_TYPES = ['DDoS', 'Malware', 'Phishing', 'Brute Force', 'SQL Injection', 'XSS'];
const ARC_COLORS = [
  ['#ff2a6d', '#ff6b9d'],
  ['#00f0ff', '#00a8cc'],
  ['#fcee0a', '#ff9e00'],
  ['#05ffa1', '#00cc80'],
  ['#8b72ff', '#b69fff'],
];

export function CyberGlobe({ width = 600, height = 500 }: { width?: number; height?: number }) {
  const globeRef = useRef<any>(null);
  const [arcs, setArcs] = useState<ArcData[]>([]);
  const [points, setPoints] = useState<PointData[]>([]);
  const [hoverArc, setHoverArc] = useState<ArcData | null>(null);
  useEffect(() => {
    const cityPoints: PointData[] = CITIES.map((city) => ({
      lat: city.lat,
      lng: city.lng,
      size: 0.3 + Math.random() * 0.4,
      color: ['#00f0ff', '#ff2a6d', '#05ffa1', '#fcee0a'][Math.floor(Math.random() * 4)] ?? '#00f0ff',
      name: city.name,
    }));
    setPoints(cityPoints);
  }, []);

  const generateArc = useCallback((): ArcData => {
    const srcIdx = Math.floor(Math.random() * CITIES.length);
    let dstIdx = Math.floor(Math.random() * CITIES.length);
    while (dstIdx === srcIdx) {
      dstIdx = Math.floor(Math.random() * CITIES.length);
    }
    const src = CITIES[srcIdx]!;
    const dst = CITIES[dstIdx]!;
    const colors = ARC_COLORS[Math.floor(Math.random() * ARC_COLORS.length)]!;
    const threatType = THREAT_TYPES[Math.floor(Math.random() * THREAT_TYPES.length)]!;
    return {
      startLat: src.lat,
      startLng: src.lng,
      endLat: dst.lat,
      endLng: dst.lng,
      color: colors,
      threatType,
    };
  }, []);

  useEffect(() => {
    // Initial arcs — fewer
    const initial = Array.from({ length: 4 }, generateArc);
    setArcs(initial);

    // Add new arcs less frequently
    const interval = setInterval(() => {
      setArcs((prev) => {
        const updated = [...prev, generateArc()];
        return updated.slice(-8); // Keep last 8 arcs (was 15)
      });
    }, 4000); // was 2500ms

    return () => clearInterval(interval);
  }, [generateArc]);

  // Auto-rotate
  useEffect(() => {
    if (globeRef.current) {
      const controls = globeRef.current.controls();
      if (controls) {
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.5;
      }
    }
  }, []);

  return (
    <div className="cyber-globe relative">
      <Globe
        ref={globeRef}
        width={width}
        height={height}
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        backgroundImageUrl=""
        backgroundColor="rgba(0,0,0,0)"
        atmosphereColor="#00f0ff"
        atmosphereAltitude={0.15}
        arcsData={arcs}
        arcStartLat="startLat"
        arcStartLng="startLng"
        arcEndLat="endLat"
        arcEndLng="endLng"
        arcColor="color"
        arcDashLength={0.4}
        arcDashGap={0.2}
        arcDashAnimateTime={1500}
        arcStroke={0.8}
        arcAltitudeAutoScale={0.3}
        pointsData={points}
        pointLat="lat"
        pointLng="lng"
        pointColor="color"
        pointAltitude={0.01}
        pointRadius="size"
        pointsMerge={false}
        onArcHover={(arc: any) => setHoverArc(arc)}
        showGraticules={false}
        showAtmosphere={true}
      />

      {/* HUD overlay */}
      <div className="pointer-events-none absolute inset-0">
        {/* Corner brackets */}
        <div className="absolute left-2 top-2 h-6 w-6 border-l border-t border-cyan/50" />
        <div className="absolute right-2 top-2 h-6 w-6 border-r border-t border-cyan/50" />
        <div className="absolute bottom-2 left-2 h-6 w-6 border-b border-l border-cyan/50" />
        <div className="absolute bottom-2 right-2 h-6 w-6 border-b border-r border-cyan/50" />
      </div>

      {/* Tooltip */}
      {hoverArc && (
        <div className="absolute bottom-4 left-4 rounded border border-cyan/30 bg-base/90 px-3 py-2 font-mono text-caption text-cyan backdrop-blur-sm">
          THREAT: {hoverArc.threatType}
        </div>
      )}

      {/* Stats overlay */}
      <div className="absolute right-4 top-4 font-mono text-caption">
        <div className="text-cyan">ACTIVE ARCS: {arcs.length}</div>
        <div className="text-green">NODES: {points.length}</div>
        <div className="text-yellow">STATUS: MONITORING</div>
      </div>
    </div>
  );
}