// components/AnimatedLineChart.tsx

import { LineChart } from '@mui/x-charts/LineChart';
import { motion, useAnimation } from 'framer-motion';
import { useEffect } from 'react';
import { GraidientBackground, getTheme, ChartTheme } from './gradientbackground';
import type { LineChartData } from '../types/chart';

interface Props {
  data: LineChartData;
  width?: number;
  height?: number;
  durationSeconds?: number;
  onAnimationComplete?: () => void;
}

export function AnimatedLineChart({
  data,
  width = 1280,
  height = 720,
  durationSeconds = 4,
  onAnimationComplete,
}: Props) {

  const theme: ChartTheme = data.theme ?? 'heaven';
  const t = getTheme(theme);
  const controls = useAnimation();

  const isPortrait = height > width;

  // Card dimensions
  const cardW  = isPortrait ? width - 48 : Math.min(920, width - 48);
  const cardH  = isPortrait ? Math.round(height * 0.38) : 560;
  const chartW = cardW - 80;
  const chartH = cardH - 100;

  // Card bottom sits exactly at the vertical midpoint of the canvas.
  // top (of card) = midpoint - cardH
  const midpoint = Math.round(height * 0.65);
  const topPx    = isPortrait ? midpoint - cardH : Math.round(height * 0.5) - 280;

  useEffect(() => {
    const timer = setTimeout(() => {
      controls.start({
        opacity: 1,
        transition: { duration: durationSeconds }
      });
      setTimeout(() => {
        onAnimationComplete?.();
      }, durationSeconds * 1000);
    }, 200);
    return () => clearTimeout(timer);
  }, [controls, durationSeconds, onAnimationComplete]);

  return (
    <GraidientBackground theme={theme}>

      <div
        style={{
          position: 'absolute',
          top: topPx,
          left: '50%',
          transform: 'translateX(-50%)',
          width: cardW,
          height: cardH,
          borderRadius: 16,
          background: t.cardBg,
          border: t.border,
          boxShadow: t.shadow,
          padding: 40,
          fontFamily: t.font,
          boxSizing: 'border-box',
        }}
      >
        <motion.div initial={{ opacity: 0 }} animate={controls}>
          <LineChart
            width={chartW}
            height={chartH}
            xAxis={[{
              scaleType: 'point',
              data: data.xAxis,
              tickLabelStyle: {
                fill: t.ticks,
                fontSize: 14,        // up from 11
                fontFamily: t.font,
              },
              tickNumber: 6,
            }]}
            yAxis={[{
              tickLabelStyle: {
                fill: t.ticks,
                fontSize: 14,        // up from 11
                fontFamily: t.font,
              },
              tickNumber: 5,
            }]}
            series={data.series.map(s => ({
              data: s.data,
              color: t.accent,
              showMark: true,
              area: true,
              curve: 'catmullRom'
            }))}
            sx={{
              '& .MuiLineElement-root': { strokeWidth: 3 },
              '& .MuiMarkElement-root': { r: 5, fill: t.accent },
              '& .MuiChartsGrid-line':  { stroke: t.grid, strokeDasharray: '4 4' },
              // Axis label font size (the unit label e.g. "$M")
              '& .MuiChartsAxis-label': {
                fontSize: '15px !important',
                fill: `${t.ticks} !important`,
              },
              backgroundColor: 'transparent',
            }}
          />
        </motion.div>
      </div>

    </GraidientBackground>
  );
}