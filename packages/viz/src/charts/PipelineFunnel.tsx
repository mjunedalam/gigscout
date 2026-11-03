import type { LeadStatus } from "@gigscout/api-client";

import { funnelBars } from "../layout";
import { STATUS_COLORS } from "../palette";

interface PipelineFunnelProps {
  stages: { stage: string; count: number }[];
}

/** Sales pipeline as centred, tapering bars with stage-to-stage conversion. Plain HTML: crisp and accessible. */
export function PipelineFunnel({ stages }: PipelineFunnelProps) {
  const bars = funnelBars(stages);
  return (
    <ol className="gs-funnel" aria-label="Sales pipeline funnel">
      {bars.map((bar, i) => (
        <li key={bar.stage} className="gs-funnel-row">
          <span className="gs-funnel-label">{bar.stage}</span>
          <span className="gs-funnel-track">
            <span
              className="gs-funnel-bar gs-grow-x"
              style={{
                width: `${Math.max(bar.width * 100, bar.count ? 3 : 0)}%`,
                background: STATUS_COLORS[bar.stage as LeadStatus] ?? "var(--gs-text-muted)",
                animationDelay: `${i * 60}ms`,
              }}
            />
          </span>
          <span className="gs-funnel-count">{bar.count}</span>
          <span className="gs-funnel-rate">{bar.conversion === null ? "" : `${Math.round(bar.conversion * 100)}%`}</span>
        </li>
      ))}
    </ol>
  );
}
