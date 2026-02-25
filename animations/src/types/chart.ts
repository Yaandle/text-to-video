// types/chart.ts
// Mirrors the data_schema definitions in component_catalogue.json.
// Both the Python parsers (agent_context.py) and the React components
// must conform to these shapes.

export type Theme = 'dark' | 'heaven';

// ---------------------------------------------------------------------------
// Line Chart
// ---------------------------------------------------------------------------

export interface LineSeries {
  label: string;
  data: number[];
}

export interface LineChartData {
  title?: string;
  theme?: Theme;
  yAxisLabel?: string;
  xAxis: string[];
  series: LineSeries[];
}

// ---------------------------------------------------------------------------
// Scatter Chart
// ---------------------------------------------------------------------------

export interface ScatterPoint {
  x: number;
  y: number;
}

export interface ScatterSeries {
  label: string;
  data: ScatterPoint[];
}

export interface ScatterChartData {
  title?: string;
  theme?: Theme;
  xAxisLabel?: string;
  yAxisLabel?: string;
  series: ScatterSeries[];
}

// ---------------------------------------------------------------------------
// Pie / Donut Chart
// ---------------------------------------------------------------------------

export interface PieSegment {
  label: string;
  value: number;
}

export interface PieChartData {
  title?: string;
  theme?: Theme;
  variant?: 'pie' | 'donut';
  data: PieSegment[];
}

// ---------------------------------------------------------------------------
// Render payload (matches what animation_visualiser.py writes as JSON)
// ---------------------------------------------------------------------------

export type ChartData = LineChartData | ScatterChartData | PieChartData;

export interface RenderPayload {
  componentId: 'line_animated' | 'scatter_animated' | 'pie_animated';
  data: ChartData;
  width: number;
  height: number;
  durationSeconds: number;
  framesDir: string;
}