import type { AnalystAnswer, Insight } from "@gigscout/api-client";
import { Badge, Button, Group, List, Paper, Skeleton, Stack, Text, TextInput, ThemeIcon } from "@mantine/core";
import { IconBulb, IconSparkles, IconTrendingDown, IconTrendingUp, IconAlertTriangle } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { api, messageOf } from "../../lib/api";
import { Panel } from "../layout-bits";

const KIND: Record<Insight["kind"], { color: string; icon: ReactNode }> = {
  up: { color: "teal", icon: <IconTrendingUp size={14} /> },
  down: { color: "red", icon: <IconTrendingDown size={14} /> },
  warning: { color: "orange", icon: <IconAlertTriangle size={14} /> },
  tip: { color: "violet", icon: <IconBulb size={14} /> },
};
const SUGGESTIONS = ["Why did replies change?", "Which source should we run more?", "Where do leads get stuck?"];

/** What moved in the period (computed), and a place to ask about the numbers (answered from them only). */
export function AnalystPanel({ days, compact = false }: { days: number; compact?: boolean }) {
  const insights = useQuery({ queryKey: ["reports", "insights", days], queryFn: () => api.analyst.insights(days) });
  const [question, setQuestion] = useState("");
  const ask = useMutation({ mutationFn: (q: string) => api.analyst.ask(q, days) });
  const items = (insights.data?.insights ?? []).slice(0, compact ? 3 : 8);
  const submit = (q: string) => { setQuestion(q); if (q.trim().length >= 3) ask.mutate(q.trim()); };

  return (
    <Panel eyebrow="AI analyst" title="What changed, and why"
      actions={<Badge variant="light" color="gray">{days} days vs the {days} before</Badge>}>
      <Stack gap="sm">
        {insights.isPending && <Skeleton h={80} />}
        {insights.data && items.length === 0 && <Text size="sm" c="var(--gs-text-muted)">Nothing moved enough to stand out in this period.</Text>}
        {items.map((i) => (
          <Group key={i.text} gap="xs" wrap="nowrap" align="flex-start">
            <ThemeIcon size={22} radius="xl" variant="light" color={KIND[i.kind].color}>{KIND[i.kind].icon}</ThemeIcon>
            <Text size="sm">{i.text}</Text>
          </Group>
        ))}
        {!compact && (
          <>
            <form onSubmit={(e) => { e.preventDefault(); submit(question); }}>
              <Group gap="xs" wrap="nowrap" mt="xs">
                <TextInput style={{ flex: 1 }} placeholder="Ask about these numbers…" maxLength={500} value={question}
                  onChange={(e) => setQuestion(e.currentTarget.value)} leftSection={<IconSparkles size={14} />} />
                <Button type="submit" loading={ask.isPending} disabled={question.trim().length < 3}>Ask</Button>
              </Group>
            </form>
            <Group gap={6}>
              {SUGGESTIONS.map((s) => <Button key={s} size="compact-xs" variant="light" color="gray" onClick={() => submit(s)}>{s}</Button>)}
            </Group>
            {ask.isError && <Text size="sm" c="red">{messageOf(ask.error)}</Text>}
            {ask.data && <Answer a={ask.data} />}
          </>
        )}
      </Stack>
    </Panel>
  );
}

function Answer({ a }: { a: AnalystAnswer }) {
  return (
    <Paper withBorder radius="md" p="sm" className="gs-fade-in">
      <Stack gap={6}>
        <Text size="sm">{a.answer}</Text>
        {a.evidence.length > 0 && (
          <>
            <Text size="xs" fw={600} c="var(--gs-text-muted)">Based on</Text>
            <List size="xs" spacing={2}>{a.evidence.map((e) => <List.Item key={e}>{e}</List.Item>)}</List>
          </>
        )}
        {a.actions.length > 0 && (
          <>
            <Text size="xs" fw={600} c="var(--gs-text-muted)">Next steps</Text>
            <List size="xs" spacing={2}>{a.actions.map((e) => <List.Item key={e}>{e}</List.Item>)}</List>
          </>
        )}
        <Text size="xs" c="var(--gs-text-dim)">{a.by === "ai" ? "Written by the AI from the report's numbers" : "From the computed insights (AI not running)"}</Text>
      </Stack>
    </Paper>
  );
}
