import type { Claim, Evidence } from "@gigscout/api-client";
import { Anchor, Badge, Button, Group, HoverCard, List, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconAlertTriangle, IconBook2, IconCircleCheck, IconRefresh } from "@tabler/icons-react";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { api, messageOf } from "../../lib/api";

interface GroundingProps {
  evidence: Evidence[] | null | undefined;
  claims: Claim[] | null | undefined;
  /** The text as it is on screen now, to check again after an edit. */
  body: string;
}

/** What a pitch is built on: the company's own documents it cites, and which of its claims they back. */
export function Grounding({ evidence, claims: saved, body }: GroundingProps) {
  const [claims, setClaims] = useState(saved);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setClaims(saved), [saved]);
  const recheck = useMutation({
    mutationFn: () => api.knowledge.check(body),
    onSuccess: (r) => { setClaims(r.claims); setError(null); },
    onError: (e) => setError(messageOf(e)),
  });

  if (saved === null || saved === undefined) {
    return (
      <Text size="xs" c="var(--gs-text-muted)">
        <IconBook2 size={12} style={{ verticalAlign: -2 }} /> Add case studies to the{" "}
        <Anchor component={Link} to="/knowledge" size="xs">knowledge base</Anchor> and pitches cite your real work, with every claim checked.
      </Text>
    );
  }
  const unbacked = (claims ?? []).filter((c) => !c.supported);
  const backed = (claims ?? []).length - unbacked.length;

  return (
    <Stack gap={6} className="gs-grounding">
      <Group gap={6} wrap="wrap">
        <Text size="xs" c="var(--gs-text-muted)">Built on:</Text>
        {evidence && evidence.length > 0 ? evidence.map((e) => (
          <HoverCard key={`${e.doc_id}-${e.excerpt.slice(0, 12)}`} width={320} shadow="md" openDelay={150}>
            <HoverCard.Target>
              <Badge size="sm" variant="outline" color="gray" leftSection={<IconBook2 size={10} />} style={{ cursor: "help" }}>
                {e.title}
              </Badge>
            </HoverCard.Target>
            <HoverCard.Dropdown>
              <Text size="xs" fw={600}>{e.title} · {Math.round(e.similarity * 100)}% match</Text>
              <Text size="xs" c="var(--gs-text-muted)" mt={4}>“{e.excerpt}…”</Text>
            </HoverCard.Dropdown>
          </HoverCard>
        )) : <Text size="xs" c="var(--gs-text-muted)">nothing in your documents matched this lead</Text>}
      </Group>
      <Group gap={6} justify="space-between" wrap="wrap">
        <Group gap={6}>
          {backed > 0 && <Badge size="sm" color="teal" variant="light" leftSection={<IconCircleCheck size={10} />}>{backed} claim{backed === 1 ? "" : "s"} backed</Badge>}
          {unbacked.length > 0 && <Badge size="sm" color="orange" variant="light" leftSection={<IconAlertTriangle size={10} />}>{unbacked.length} not in your documents</Badge>}
          {(claims ?? []).length === 0 && <Text size="xs" c="var(--gs-text-muted)">No claims about your company to check.</Text>}
        </Group>
        <Button size="compact-xs" variant="subtle" leftSection={<IconRefresh size={12} />} loading={recheck.isPending}
          onClick={() => recheck.mutate()}>Check again</Button>
      </Group>
      {unbacked.length > 0 && (
        <List size="xs" spacing={2} icon={<ThemeIcon size={14} radius="xl" color="orange" variant="light"><IconAlertTriangle size={9} /></ThemeIcon>}>
          {unbacked.map((c) => <List.Item key={c.sentence}><Text size="xs" span>{c.sentence}</Text></List.Item>)}
        </List>
      )}
      {error && <Text size="xs" c="red">{error}</Text>}
    </Stack>
  );
}
