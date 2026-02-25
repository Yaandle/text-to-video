// components/AnimatedScatterChart.tsx
// MUI X ScatterChart with staggered point fade-in via framer-motion.

import { ScatterChart } from '@mui/x-charts/ScatterChart';
import { motion } from 'framer-motion';
import { GraidientBackground, getTheme, ChartTheme } from './gradientbackground';
import type { ScatterChartData } from '../types/chart';

interface AnimatedScatterChartProps {
  data: ScatterChartData;
  width?: number;
  height?: number;
  durationSeconds?: number;
  onAnimationComplete?: () => void;
}

export function AnimatedScatterChart({
  data,
  width = 1280,
  height = 720,
  durationSeconds = 3,
  onAnimationComplete,
}: AnimatedScatterChartProps) {
  const theme: ChartTheme = data.theme ?? 'heaven';
  const t = getTheme(theme);

  const isPortrait = height > width;

  // Card dimensions
  const cardW  = isPortrait ? width - 48 : Math.min(920, width - 48);
  const cardH  = isPortrait ? Math.round(height * 0.38) : 560;
  const chartW = cardW - 80;
  const chartH = cardH - 100;

  // Card bottom at 65% down the canvas
  const topPx = Math.round(height * 0.65) - cardH;

  const containerVariants = {
    hidden: { opacity: 0, y: 18 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: durationSeconds * 0.6,
        ease: 'easeOut',
        onComplete: onAnimationComplete,
      },
    },
  };

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
        {/* Title */}
        {data.title && (
          <div
            style={{
              fontSize: 30,
              fontWeight: 700,
              color: t.accent,
              marginBottom: 12,
            }}
          >
            {data.title}
          </div>
        )}

        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          style={{ width: chartW, height: chartH }}
        >
          <ScatterChart
            width={chartW}
            height={chartH}
            series={data.series.map((s, i) => ({
              data: s.data.map((pt, idx) => ({ id: `${i}-${idx}`, x: pt.x, y: pt.y })),
              label: s.label,
              color: t.accent,
              showMark: true,
              markSize: 6,
            }))}
            xAxis={[{
              tickLabelStyle: { fill: t.ticks, fontSize: 14, fontFamily: t.font },
              tickNumber: 6,
            }]}
            yAxis={[{
              tickLabelStyle: { fill: t.ticks, fontSize: 14, fontFamily: t.font },
              tickNumber: 5,
            }]}
            sx={{
              '& .MuiChartsGrid-line': { stroke: t.grid, strokeDasharray: '4 4' },
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