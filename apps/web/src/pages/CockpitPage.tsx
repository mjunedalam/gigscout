import { Alert, Button, Center, Loader, SegmentedControl, Stack, Text, useComputedColorScheme } from "@mantine/core";
import { IconPlayerPlay } from "@tabler/icons-react";
import { lazy, Suspense, useState } from "react";

import { AgentCards, CockpitCharts, KpiStrip, LiveFeed } from "../components/cockpit/CockpitPanels";
import { useCockpit } from "../components/cockpit/useCockpit";
import { StartRunButton } from "../components/StartRunButton";
import "../components/cockpit/cockpit.css";

const ProductionLine = lazy(() => import("@gigscout/viz/factory"));

const MODE_LABEL = { idle: "", loading: "Loading…", live: "Live", replay: "Replay", error: "Error" } as const;

/**
 * Agent cockpit: the run in progress as a production line (or the latest run, replayed), with live totals,
 * what each agent is doing, and charts of where the leads went.
 */
export default function CockpitPage() {
  const { run, mode, model, error, replay } = useCockpit();
  const [camera, setCamera] = useState<"follow" | "overview">("follow");
  const dark = useComputedColorScheme("dark") === "dark";

  if (mode === "idle") {
    return (
      <Center h="60vh">
        <Stack align="center" gap="sm">
          <Text fw={600} size="lg">No runs yet</Text>
          <Text c="var(--gs-text-muted)" size="sm">Start a run to watch your agents build the line and qualify leads live.</Text>
          <StartRunButton />
        </Stack>
      </Center>
    );
  }

  const controls = (
    <>
      <Text size="xs" fw={700} c={mode === "live" ? "signal" : "var(--gs-text-muted)"}>
        {mode === "live" ? "● " : ""}{MODE_LABEL[mode]}{run ? ` · ${run.mode ?? run.mode_requested}` : ""}
      </Text>
      {mode === "replay" && (
        <Button size="compact-xs" variant="light" leftSection={<IconPlayerPlay size={12} />} onClick={replay}>Replay</Button>
      )}
    </>
  );

  return (
    <div className="gs-cockpit">
      <KpiStrip model={model} run={run} controls={controls} />
      <aside className="gs-cockpit-side">
        <AgentCards model={model} />
        <LiveFeed model={model} />
      </aside>
      <main className="gs-panel gs-cockpit-stage">
        <span className="gs-eyebrow cap">Production line · stations rise when their step starts</span>
        <SegmentedControl className="cam" size="xs" value={camera} onChange={(v) => setCamera(v as typeof camera)}
          data={[{ label: "Follow active", value: "follow" }, { label: "Overview", value: "overview" }]} />
        {error && <Alert color="red" m="xl">{error}</Alert>}
        <Suspense fallback={<Center h="100%"><Loader type="dots" /></Center>}>
          <ProductionLine model={model} runKey={run?.id ?? null} follow={camera === "follow"} dark={dark} />
        </Suspense>
      </main>
      <CockpitCharts model={model} />
    </div>
  );
}
