import type { HoodStep } from "@gigscout/api-client";
import { AGENT_COLORS, AGENT_NAMES } from "@gigscout/viz";
import { Alert, Badge, Code, Divider, Drawer, Group, Spoiler, Stack, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import type { ReactNode } from "react";

import { OP_ICON, OP_LABEL } from "./ops";
import { millis } from "./steps";

const ROLE_LABEL: Record<string, string> = { system: "Instructions", user: "Asked", assistant: "Agent said", tool: "Tool result" };

/** Everything about one under-the-hood step: what went in, what came out, how long it took. */
export function HoodDrawer({ step, onClose }: { step: HoodStep | null; onClose: () => void }) {
  return (
    <Drawer opened={step !== null} onClose={onClose} position="right" size="lg" title={<span className="gs-eyebrow">Under the hood</span>}>
      {step && <HoodDetail step={step} />}
    </Drawer>
  );
}

function HoodDetail({ step }: { step: HoodStep }) {
  const d = step.detail;
  const tokens = (d.tokens_in ?? 0) + (d.tokens_out ?? 0);
  return (
    <Stack gap="md">
      <div>
        <Group gap="xs" mb={6}>
          <Badge variant="light" color={AGENT_COLORS[step.agent]}>{AGENT_NAMES[step.agent]}</Badge>
          <Badge variant="default" leftSection={OP_ICON[step.op]}>{OP_LABEL[step.op]}</Badge>
        </Group>
        <Text fw={600} size="lg" className="gs-display">{step.title}</Text>
      </div>
      <Group gap="lg" className="gs-hood-facts">
        {step.ms !== null && <Fact label="Took" value={millis(step.ms)} />}
        {d.model && <Fact label="Model" value={d.model} />}
        {tokens > 0 && <Fact label="Tokens" value={`${d.tokens_in ?? 0} in · ${d.tokens_out ?? 0} out`} />}
        {d.source && <Fact label="Source" value={d.source} />}
        {d.results !== undefined && <Fact label="Results" value={String(d.results)} />}
        {d.k !== undefined && <Fact label="Closest asked for" value={String(d.k)} />}
        {d.excluded ? <Fact label="Excluded by profile" value={String(d.excluded)} /> : null}
      </Group>
      {d.error && <Alert color="red" variant="light" icon={<IconAlertTriangle size={16} />} title="It failed">{d.error}</Alert>}

      {d.messages && d.messages.length > 0 && (
        <Section title="What the AI was given">
          {d.earlier_messages ? <Text size="xs" c="var(--gs-text-muted)">{d.earlier_messages} earlier messages not shown</Text> : null}
          {d.messages.map((m, i) => (
            <div key={i} className="gs-hood-msg" data-role={m.role}>
              <Text size="xs" fw={600} c="var(--gs-text-muted)" mb={4}>{ROLE_LABEL[m.role] ?? m.role}</Text>
              <Spoiler maxHeight={m.role === "system" ? 72 : 180} showLabel="Show all" hideLabel="Show less">
                <Text size="sm" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{m.text}</Text>
              </Spoiler>
            </div>
          ))}
        </Section>
      )}
      {(d.reply || d.tool_calls) && (
        <Section title="What it answered">
          {d.reply && (
            <Spoiler maxHeight={220} showLabel="Show all" hideLabel="Show less">
              <Code block style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{d.reply}</Code>
            </Spoiler>
          )}
          {d.tool_calls?.map((c, i) => (
            <div key={i}>
              <Text size="sm" mb={4}>Decided to call <b className="gs-mono">{c.tool}</b> with:</Text>
              <Code block style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{JSON.stringify(c.args, null, 2)}</Code>
            </div>
          ))}
        </Section>
      )}
      {d.tool && (
        <Section title={`Tool: ${d.tool}`}>
          <Text size="xs" c="var(--gs-text-muted)">Input</Text>
          <Code block style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{typeof d.args === "string" ? d.args : JSON.stringify(d.args, null, 2)}</Code>
          {d.result !== undefined && (
            <>
              <Text size="xs" c="var(--gs-text-muted)">What the agent read back</Text>
              <Spoiler maxHeight={220} showLabel="Show all" hideLabel="Show less">
                <Code block style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{d.result}</Code>
              </Spoiler>
            </>
          )}
        </Section>
      )}
      {(d.queries || d.query) && (
        <Section title={step.op === "memory" ? "Searched memory for" : "Searched for"}>
          {d.queries && <Group gap={6}>{d.queries.map((q) => <Badge key={q} variant="default" tt="none" className="gs-mono">{q}</Badge>)}</Group>}
          {d.query && <Code block style={{ whiteSpace: "pre-wrap" }}>{d.query}</Code>}
        </Section>
      )}
      {d.sample && d.sample.length > 0 && (
        <Section title="First results">
          {d.sample.map((title) => <Text key={title} size="sm">• {title}</Text>)}
        </Section>
      )}
    </Stack>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Text size="xs" c="var(--gs-text-muted)">{label}</Text>
      <Text size="sm" fw={600} className="gs-mono">{value}</Text>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Stack gap={8}>
      <Divider label={title} labelPosition="left" />
      {children}
    </Stack>
  );
}
