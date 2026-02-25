// components/AnimatedPieChart.tsx
// MUI X PieChart with sweep-in animation via framer-motion orchestration.

import { PieChart } from '@mui/x-charts/PieChart';
import { motion } from 'framer-motion';
import { GraidientBackground, getTheme, ChartTheme } from './gradientbackground';
import type { PieChartData } from '../types/chart';

interface AnimatedPieChartProps {
  data: PieChartData;
  width?: number;
  height?: number;
  durationSeconds?: number;
  onAnimationComplete?: () => void;
}

export function AnimatedPieChart({
  data,
  width = 1280,
  height = 720,
  durationSeconds = 3,
  onAnimationComplete,
}: AnimatedPieChartProps) {
  const theme: ChartTheme = data.theme ?? 'heaven';
  const t = getTheme(theme);
  const variant = data.variant ?? 'donut';
  const palette = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4'];

  const isPortrait = height > width;

  // Card dimensions
  const cardW  = isPortrait ? width - 48 : Math.min(920, width - 48);
  const cardH  = isPortrait ? Math.round(height * 0.38) : 560;
  const chartW = cardW - 80;
  const chartH = cardH - 100;

  // Card bottom at 65% down the canvas
  const topPx = Math.round(height * 0.65) - cardH;

  const innerRadius = variant === 'donut' ? 90 : 0;
  const total = data.data.reduce((sum, s) => sum + s.value, 0);

  const containerVariants = {
    hidden: { opacity: 0, scale: 0.85 },
    visible: {
      opacity: 1,
      scale: 1,
      transition: {
        duration: durationSeconds * 0.65,
        ease: [0.34, 1.56, 0.64, 1],
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
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        {/* Title */}
        {data.title && (
          <div
            style={{
              fontFamily: t.font,
              fontSize: 30,
              fontWeight: 700,
              color: t.accent,
              marginBottom: 16,
              alignSelf: 'flex-start',
            }}
          >
            {data.title}
          </div>
        )}

        {/* Chart + donut centre label */}
        <div
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flex: 1,
            width: '100%',
          }}
        >
          {variant === 'donut' && (
            <div
              style={{
                position: 'absolute',
                textAlign: 'center',
                pointerEvents: 'none',
                fontFamily: t.font,
                color: t.ticks,
              }}
            >
              <div style={{ fontSize: 14, opacity: 0.6 }}>Total</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>
                {total.toLocaleString()}
              </div>
            </div>
          )}

          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            <PieChart
              width={chartW}
              height={chartH}
              series={[{
                data: data.data.map((seg, i) => ({
                  id: i,
                  value: seg.value,
                  label: `${seg.label} (${Math.round((seg.value / total) * 100)}%)`,
                  color: palette[i % palette.length],
                })),
                innerRadius,
                paddingAngle: variant === 'donut' ? 3 : 1,
                cornerRadius: variant === 'donut' ? 6 : 2,
              }]}
              sx={{
                backgroundColor: 'transparent',
                '& .MuiChartsLegend-label': {
                  fontSize: '14px !important',
                  fill: `${t.ticks} !important`,
                  fontFamily: `${t.font} !important`,
                },
              }}
            />
          </motion.div>
        </div>
      </div>

    </GraidientBackground>
  );
}