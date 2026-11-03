import type { SourceTestResult } from "@gigscout/api-client";
import { Alert, Badge, Box, Button, Code, Group, SimpleGrid, Skeleton, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconCloudDownload, IconMailbox, IconPlayerPlay } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "../../components/layout-bits";
import { api, messageOf } from "../../lib/api";

export default function AdminSourcesPage() {
  const sources = useQuery({ queryKey: ["admin", "sources"], queryFn: api.admin.sources });
  const [results, setResults] = useState<Record<string, SourceTestResult>>({});
  const test = useMutation({
    mutationFn: api.admin.testSource,
    onSuccess: (result) => setResults((r) => ({ ...r, [result.name]: result })),
  });

  return (
    <>
      <PageHeader eyebrow="Admin" title="Lead sources"
        description="Pull sources are searched by the agents; push channels deliver leads to the webhook. Failures come from the last 20 runs." />
      {sources.isError && <Alert color="red">{messageOf(sources.error)}</Alert>}
      {sources.isPending && <Skeleton h={260} radius="lg" />}
      <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md" className="gs-stagger">
        {sources.data?.map((s) => {
          const result = results[s.name];
          const healthy = s.enabled && s.recent_failures === 0;
          return (
            <Box key={s.name} className="gs-panel gs-lift" p="lg">
              <Group justify="space-between" wrap="nowrap">
                <Group gap="sm" wrap="nowrap">
                  <ThemeIcon radius="xl" variant="light" color={healthy ? "signal" : s.enabled ? "orange" : "gray"}>
                    {s.channel === "pull" ? <IconCloudDownload size={18} /> : <IconMailbox size={18} />}
                  </ThemeIcon>
                  <Stack gap={0}>
                    <Text fw={600} className="gs-mono">{s.name}</Text>
                    <Text size="xs" c="var(--gs-text-muted)">{s.channel === "pull" ? "searched by agents" : "pushes via webhook"}</Text>
                  </Stack>
                </Group>
                <Badge color={healthy ? "signal" : s.enabled ? "orange" : "gray"} variant="light">
                  {!s.enabled ? "disabled" : s.recent_failures ? `${s.recent_failures} failures` : "healthy"}
                </Badge>
              </Group>
              {s.last_error && <Code block mt="md" style={{ whiteSpace: "pre-wrap" }}>{s.last_error}</Code>}
              {result && (
                <Alert mt="md" variant="light" color={result.ok ? "signal" : "red"} title={result.ok ? `${result.count} results in ${result.latency_ms} ms` : "Test failed"}>
                  {result.ok ? result.sample.map((t) => <Text key={t} size="xs" lineClamp={1}>• {t}</Text>) : result.error}
                </Alert>
              )}
              {s.channel === "pull" && (
                <Button mt="md" size="xs" variant="light" leftSection={<IconPlayerPlay size={14} />}
                  loading={test.isPending && test.variables === s.name} onClick={() => test.mutate(s.name)}>
                  Test now
                </Button>
              )}
            </Box>
          );
        })}
      </SimpleGrid>
    </>
  );
}
