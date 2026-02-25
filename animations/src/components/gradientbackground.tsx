// components/GrainientBackground.tsx
// Theme-driven grain + bleed background for portrait 1080x1920 renders.

import { useEffect, useRef } from 'react';

export type ChartTheme = 'heaven' | 'dark' | 'matrix';

interface GraidientBackgroundProps {
  theme?: ChartTheme;
  children: React.ReactNode;
  width?: number;
  height?: number;
}

const THEMES = {
  heaven: {
    background: 'radial-gradient(circle at center, #f0eeea 0%, #ddd8d0 100%)',
    grain: 0.03,
    cardBg: 'rgba(255, 253, 248, 0.85)',
    border: '1px solid rgba(200,169,110,0.25)',
    shadow: '0 0 60px rgba(200,169,110,0.08)',
    accent: '#c8a96e',
    secondary: '#a07840',
    muted: '#e8dcc8',
    grid: 'rgba(180,160,120,0.15)',
    ticks: 'rgba(100,80,50,0.6)',
    font: `'Playfair Display', 'Georgia', serif`,
    palette: ['#c8a96e','#b09060','#987850','#806040','#684830','#503020']
  },

  dark: {
    background: 'radial-gradient(circle at center, #080808 0%, #000000 100%)',
    grain: 0.08,
    cardBg: 'rgba(12,12,12,0.9)',
    border: '1px solid rgba(255,255,255,0.08)',
    shadow: '0 0 60px rgba(255,255,255,0.03)',
    accent: '#e0e0e0',
    secondary: '#a0a0a0',
    muted: '#404040',
    grid: 'rgba(255,255,255,0.06)',
    ticks: 'rgba(255,255,255,0.35)',
    font: `'JetBrains Mono', 'Fira Code', monospace`,
    palette: ['#e0e0e0','#b0b0b0','#808080','#505050','#303030','#181818']
  },

  matrix: {
    background: 'radial-gradient(circle at center, #080808 0%, #000000 100%)',
    grain: 0.05,
    cardBg: 'rgba(10,10,10,0.85)',
    border: '1px solid rgba(0,255,65,0.15)',
    shadow: '0 0 60px rgba(0,255,65,0.06)',
    accent: '#00ff41',
    secondary: '#00cc33',
    muted: '#004d14',
    grid: 'rgba(0,255,65,0.08)',
    ticks: 'rgba(0,255,65,0.6)',
    font: `'JetBrains Mono', 'Fira Code', monospace`,
    palette: ['#00ff41','#00cc33','#009926','#006619','#003d0f','#001a06']
  }
} as const;

export function GraidientBackground({
  theme = 'dark',
  children,
  width = 1080,
  height = 1920,
}: GraidientBackgroundProps) {

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const t = THEMES[theme];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = width;
    canvas.height = height;

    const imageData = ctx.createImageData(width, height);
    const data = imageData.data;

    for (let i = 0; i < data.length; i += 4) {
      const noise = (Math.random() - 0.5) * 255;
      data[i] = data[i+1] = data[i+2] = 128 + noise;
      data[i+3] = Math.floor(t.grain * 255);
    }

    ctx.putImageData(imageData, 0, 0);
  }, [theme, width, height, t.grain]);

  return (
    <div
      style={{
        position: 'relative',
        width,
        height,
        overflow: 'hidden',
        background: t.background,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          mixBlendMode: 'overlay',
        }}
      />

      {/* 
        CRITICAL: this wrapper must fill the full canvas (position absolute, inset 0)
        so that child cards using position:absolute resolve their top/left against
        the full width x height container, not a collapsed content-sized div.
      */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 1 }}>
        {children}
      </div>
    </div>
  );
}

export function getTheme(theme: ChartTheme) {
  return THEMES[theme];
}