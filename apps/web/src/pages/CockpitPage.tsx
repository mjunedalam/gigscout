import type { AgentKey } from "@gigscout/api-client";
import { Alert, Button, Center, Loader, SegmentedControl, Stack, Text, useComputedColorScheme } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconPlayerPlay, IconPlayerStop } from "@tabler/icons-react";
import { useMutation } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";

import { AgentCards, CockpitCharts, KpiStrip, LiveFeed } from "../components/cockpit/CockpitPanels";
import { AgentHoodDrawer } from "../components/hood/AgentHoodDrawer";
import { useCockpit } from "../components/cockpit/useCockpit";
import { StartRunButton } from "../components/StartRunButton";
import { api, messageOf } from "../lib/api";
import "../components/cockpit/cockpit.css";

const ProductionLine = lazy(() => import("@gigscout/viz/factory"));

const MODE_LABEL = { idle: "", loading: "Loading…", live: "Live", replay: "Replay", error: "Error" } as const;

/**
 * Agent cockpit: the run in progress as a production line (or the latest run, replayed), with live totals,
 * what each agent is doing, and charts of where the leads went.
 */
export default function CockpitPage() {
  const { run, mode, model, now, error, replay } = useCockpit();
  const [camera, setCamera] = useState<"follow" | "overview">("follow");
  const [peek, setPeek] = useState<AgentKey | null>(null);
  const dark = useComputedColorScheme("dark") === "dark";
  const active = run?.status === "running" || run?.status === "queued";
  const stop = useMutation({
    mutationFn: (id: string) => api.runs.cancel(id),
    onError: (e) => notifications.show({ color: "red", title: "Could not stop the run", message: messageOf(e) }),
  });
  const { reset: resetStop } = stop;
  useEffect(() => resetStop(), [run?.id, resetStop]);
  const stopping = stop.isPending || (stop.isSuccess && active);

  if (mode === "idle") {
    return (
      <Center h="60vh">
        <Stack align="center" gap="sm">
          <Text fw={600} size="lg">No runs yet</Text>
          <Text c="var(--gs-text-muted)" size="sm">Start a run to watch your agents build the line and qualify leads live.</Text>
          <StartRunButton openRun={false} />
        </Stack>
      </Center>
    );
  }

  const controls = (
    <>
      <Text size="xs" fw={700} c={mode === "live" ? "signal" : "var(--gs-text-muted)"}>
        {mode === "live" ? "● " : ""}{run?.status === "cancelled" && mode === "replay" ? "Stopped" : MODE_LABEL[mode]}
        {run ? ` · ${run.mode ?? run.mode_requested}` : ""}
      </Text>
      {active ? (
        <Button size="compact-xs" color="red" variant="light" leftSection={<IconPlayerStop size={12} />}
          loading={stop.isPending} disabled={stopping} onClick={() => run && stop.mutate(run.id)}>
          {stopping ? "Stopping…" : "Stop run"}
        </Button>
      ) : (
        <StartRunButton size="xs" openRun={false} />
      )}
      {mode === "replay" && (
        <Button size="compact-xs" variant="subtle" leftSection={<IconPlayerPlay size={12} />} onClick={replay}>Replay</Button>
      )}
    </>
  );

  return (
    <div className="gs-cockpit">
      <KpiStrip model={model} run={run} now={now} controls={controls} />
      <aside className="gs-cockpit-side">
        <AgentCards model={model} now={now} onPeek={run ? setPeek : undefined} />
        <LiveFeed model={model} />
      </aside>
      <main className="gs-panel gs-cockpit-stage">
        <span className="gs-eyebrow cap">Production line · stations rise when their step starts</span>
        <SegmentedControl className="cam" size="xs" value={camera} onChange={(v) => setCamera(v as typeof camera)}
          data={[{ label: "Follow active", value: "follow" }, { label: "Overview", value: "overview" }]} />
        {error && <Alert color="red" m="xl">{error}</Alert>}
        <Suspense fallback={<Center h="100%"><Loader type="dots" /></Center>}>
          <ProductionLine model={model} now={now} runKey={run?.id ?? null} follow={camera === "follow"} dark={dark} />
        </Suspense>
      </main>
      <CockpitCharts model={model} />
      <AgentHoodDrawer runId={run?.id ?? null} agent={peek} active={active} onClose={() => setPeek(null)} />
    </div>
  );
}
