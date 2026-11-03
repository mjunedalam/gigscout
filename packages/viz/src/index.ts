// d3 charts and helpers. The three.js scenes are separate entries ("@gigscout/viz/galaxy", "@gigscout/viz/factory")
// so apps can lazy-load them.
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
export {
  applyActivity, type CockpitLead, type CockpitModel, emptyCockpit, type FeedItem, finishCockpit, isThinking, NOT_A_MATCH,
  pileCounts, type PileCounts, type SeriesPoint, STAGE_AGENT, stageElapsed, stageProgress, stageState, type StageState,
  STAGES, type StepProgress,
} from "./cockpit/model";
export { AGENT_COLORS, AGENT_NAMES } from "./factory/layout";
export { BarList, type BarRow, LeadsOverTime } from "./cockpit/charts";
