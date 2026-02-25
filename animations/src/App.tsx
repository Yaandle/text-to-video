// App.tsx
import { AnimatedLineChart }    from './components/linechart';
import { AnimatedScatterChart } from './components/scatterchart';
import { AnimatedPieChart }     from './components/piechart';
import type {
  RenderPayload,
  LineChartData,
  ScatterChartData,
  PieChartData,
} from './types/chart';

declare global {
  interface Window {
    __RENDER_PAYLOAD__?: RenderPayload;
    __ANIMATION_COMPLETE__?: boolean;
  }
}

const DEMO_LINE: LineChartData = {
  title: 'Monthly Revenue (Demo)',
  theme: 'heaven',
  xAxis: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
  series: [
    { label: '2023', data: [4.1, 5.2, 6.0, 7.3, 8.1, 9.4] },
    { label: '2024', data: [5.0, 6.8, 7.2, 9.1, 10.3, 12.0] },
  ],
  yAxisLabel: '$M',
};

const DEMO_SCATTER: ScatterChartData = {
  title: 'Ad Spend vs Conversions (Demo)',
  theme: 'heaven',
  xAxisLabel: 'Spend ($k)',
  yAxisLabel: 'Conversions',
  series: [
    {
      label: 'Product A',
      data: [
        { x: 1.2, y: 45 }, { x: 2.4, y: 88 },
        { x: 3.1, y: 102 }, { x: 4.5, y: 140 },
      ],
    },
    {
      label: 'Product B',
      data: [
        { x: 1.0, y: 30 }, { x: 2.0, y: 55 },
        { x: 3.5, y: 90 }, { x: 5.0, y: 160 },
      ],
    },
  ],
};

const DEMO_PIE: PieChartData = {
  title: 'Market Share 2024 (Demo)',
  theme: 'heaven',
  variant: 'donut',
  data: [
    { label: 'Product A', value: 42 },
    { label: 'Product B', value: 28 },
    { label: 'Product C', value: 18 },
    { label: 'Other',     value: 12 },
  ],
};

function markComplete() {
  window.__ANIMATION_COMPLETE__ = true;
}

export default function App() {
  const payload = window.__RENDER_PAYLOAD__;

  if (payload) {
    const { componentId, data, width, height, durationSeconds } = payload;

    switch (componentId) {
      case 'line_animated':
        return (
          <AnimatedLineChart
            data={data as LineChartData}
            width={width}
            height={height}
            durationSeconds={durationSeconds}
            onAnimationComplete={markComplete}
          />
        );
      case 'scatter_animated':
        return (
          <AnimatedScatterChart
            data={data as ScatterChartData}
            width={width}
            height={height}
            durationSeconds={durationSeconds}
            onAnimationComplete={markComplete}
          />
        );
      case 'pie_animated':
        return (
          <AnimatedPieChart
            data={data as PieChartData}
            width={width}
            height={height}
            durationSeconds={durationSeconds}
            onAnimationComplete={markComplete}
          />
        );
      default:
        return <div style={{ color: 'red' }}>Unknown component: {componentId}</div>;
    }
  }

  // Dev mode
  return (
    <div style={{ background: '#1e1e1e', display: 'flex', flexDirection: 'column', gap: 24, padding: 24 }}>
      <div style={{ color: '#94a3b8', fontFamily: 'monospace', fontSize: 12, paddingBottom: 8 }}>
        DEV MODE — no render payload injected. Showing all component demos.
      </div>
      <AnimatedLineChart    data={DEMO_LINE}    width={1280} height={720} durationSeconds={4} />
      <AnimatedScatterChart data={DEMO_SCATTER} width={1280} height={720} durationSeconds={3} />
      <AnimatedPieChart     data={DEMO_PIE}     width={1280} height={720} durationSeconds={3} />
    </div>
  );
}