// d3 charts and helpers. The three.js galaxy is a separate entry ("@gigscout/viz/galaxy") so apps can lazy-load it.
export { CompetitionScatter } from "./charts/CompetitionScatter";
export { Donut, type DonutSlice } from "./charts/Donut";
export { LeadFlowChart } from "./charts/LeadFlowChart";
export { PipelineFunnel } from "./charts/PipelineFunnel";
export { RunTimeline } from "./charts/RunTimeline";
export { ScoreHistogram } from "./charts/ScoreHistogram";
export { Sparkline } from "./charts/Sparkline";
export { compactNumber, funnelBars, pushWindow, stackByKind, stackMax } from "./layout";
export { KIND_COLORS, KIND_LABELS, RUN_STATUS_COLORS, scoreColor, STATUS_COLORS } from "./palette";
export { usePrefersReducedMotion, useSize } from "./useSize";
