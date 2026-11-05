import type { Evidence, KnowledgeDoc, KnowledgeKind } from "@gigscout/api-client";
import {
  ActionIcon, Badge, Button, FileButton, Grid, Group, Select, Skeleton, Stack, Tabs, Text, Textarea, TextInput, Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconBook2, IconFileUpload, IconSearch, IconTrash, IconWritingSign } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { EmptyState, PageHeader, Panel } from "../components/layout-bits";
import { api, messageOf } from "../lib/api";
import { useAuth } from "../lib/auth";
import { timeAgo } from "../lib/format";

const KIND_LABELS: Record<KnowledgeKind, string> = {
  case_study: "Case study", proposal: "Past proposal", portfolio: "Portfolio", pricing: "Rates and pricing",
  about: "About us", other: "Other",
};
const KIND_OPTIONS = Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }));
const KEY = ["knowledge"];

/** The company's own documents. Pitches are written from them and every claim in a pitch is checked against them. */
export default function KnowledgePage() {
  const { canWrite } = useAuth();
  const list = useQuery({ queryKey: KEY, queryFn: api.knowledge.list });
  const docs = list.data?.docs ?? [];

  return (
    <>
      <PageHeader eyebrow="Intelligence" title="Knowledge base"
        description="Your case studies, past proposals, portfolio and rates. The pitch writer cites them as proof, and flags any claim they do not back."
        actions={list.data && <Badge size="lg" variant="light" color="gray">{docs.length} documents · {list.data.chunks} passages</Badge>} />
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Stack gap="md">
            {canWrite && <AddDocument />}
            <TrySearch hasDocs={docs.length > 0} />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Panel eyebrow="Library" title="What the agents know about you">
            {list.isPending && <Skeleton h={200} />}
            {list.data && docs.length === 0 && (
              <EmptyState icon={<IconBook2 size={22} />} title="No documents yet">
                Start with two or three case studies: what the client needed, what you built, and the result.
              </EmptyState>
            )}
            <Stack gap={0}>
              {docs.map((d) => <DocRow key={d.id} doc={d} canDelete={canWrite} />)}
            </Stack>
          </Panel>
        </Grid.Col>
      </Grid>
    </>
  );
}

function AddDocument() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<KnowledgeKind>("case_study");
  const [text, setText] = useState("");
  const done = (doc: KnowledgeDoc) => {
    void queryClient.invalidateQueries({ queryKey: KEY });
    notifications.show({ color: "signal", message: `Added “${doc.title}”: ${doc.chunks} passage(s) the agents can cite` });
  };
  const failed = (e: unknown) => notifications.show({ color: "red", title: "Not added", message: messageOf(e) });
  const add = useMutation({
    mutationFn: () => api.knowledge.add({ title: title.trim(), kind, text }),
    onSuccess: (doc) => { setTitle(""); setText(""); done(doc); },
    onError: failed,
  });
  const upload = useMutation({ mutationFn: (file: File) => api.knowledge.upload(file, kind), onSuccess: done, onError: failed });

  return (
    <Panel eyebrow="Add" title="Teach the agents your work">
      <Tabs defaultValue="paste" color="signal">
        <Tabs.List mb="sm">
          <Tabs.Tab value="paste" leftSection={<IconWritingSign size={14} />}>Write or paste</Tabs.Tab>
          <Tabs.Tab value="upload" leftSection={<IconFileUpload size={14} />}>Upload a file</Tabs.Tab>
        </Tabs.List>
        <Select label="Kind" data={KIND_OPTIONS} value={kind} onChange={(v) => v && setKind(v as KnowledgeKind)} allowDeselect={false} mb="sm" />
        <Tabs.Panel value="paste">
          <Stack gap="sm">
            <TextInput label="Title" placeholder="Booking platform for a clinic group" maxLength={200} value={title}
              onChange={(e) => setTitle(e.currentTarget.value)} />
            <Textarea label="Text" autosize minRows={6} maxRows={14} maxLength={200_000} value={text}
              placeholder="The client, what they needed, what you built and with what, how long it took, and the result."
              onChange={(e) => setText(e.currentTarget.value)} />
            <Group justify="flex-end">
              <Button loading={add.isPending} disabled={!title.trim() || text.trim().length < 20} onClick={() => add.mutate()}>Add</Button>
            </Group>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="upload">
          <Stack gap="xs" align="flex-start">
            <Text size="sm" c="var(--gs-text-muted)">PDF, .txt or .md, up to 10 MB. The file name becomes the title.</Text>
            <FileButton onChange={(f) => f && upload.mutate(f)} accept="application/pdf,.pdf,.txt,.md,text/plain,text/markdown">
              {(props) => <Button {...props} leftSection={<IconFileUpload size={16} />} loading={upload.isPending}>Choose a file</Button>}
            </FileButton>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Panel>
  );
}

function TrySearch({ hasDocs }: { hasDocs: boolean }) {
  const [q, setQ] = useState("");
  const search = useMutation({ mutationFn: () => api.knowledge.search(q) });
  return (
    <Panel eyebrow="Try it" title="What would the agents cite?">
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length > 1) search.mutate(); }}>
        <Group gap="xs" wrap="nowrap">
          <TextInput style={{ flex: 1 }} placeholder="A lead, e.g. React Native app for a fintech" value={q} disabled={!hasDocs}
            onChange={(e) => setQ(e.currentTarget.value)} leftSection={<IconSearch size={14} />} />
          <Button type="submit" variant="light" loading={search.isPending} disabled={!hasDocs}>Search</Button>
        </Group>
      </form>
      {search.data && <Results results={search.data.results} />}
    </Panel>
  );
}

function Results({ results }: { results: Evidence[] }) {
  if (!results.length) return <Text size="sm" mt="sm" c="var(--gs-text-muted)">Nothing close enough: the pitch would not cite past work.</Text>;
  return (
    <Stack gap="xs" mt="sm">
      {results.map((r, i) => (
        <div key={`${r.doc_id}-${i}`}>
          <Group gap={6}><Text size="sm" fw={600}>{r.title}</Text><Badge size="xs" variant="light">{Math.round(r.similarity * 100)}%</Badge></Group>
          <Text size="xs" c="var(--gs-text-muted)" lineClamp={3}>{r.excerpt}</Text>
        </div>
      ))}
    </Stack>
  );
}

function DocRow({ doc, canDelete }: { doc: KnowledgeDoc; canDelete: boolean }) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.knowledge.remove(doc.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
    onError: (e) => notifications.show({ color: "red", title: "Not removed", message: messageOf(e) }),
  });
  return (
    <Group justify="space-between" wrap="nowrap" align="flex-start" py="sm" style={{ borderBottom: "1px solid var(--gs-line)" }}>
      <Stack gap={2} style={{ minWidth: 0 }}>
        <Group gap={6} wrap="nowrap">
          <Text size="sm" fw={600} lineClamp={1}>{doc.title}</Text>
          <Badge size="xs" variant="light" color="gray">{KIND_LABELS[doc.kind] ?? doc.kind}</Badge>
        </Group>
        <Text size="xs" c="var(--gs-text-muted)" lineClamp={2}>{doc.preview}</Text>
        <Text size="xs" c="var(--gs-text-dim)">{doc.chunks} passages · added {timeAgo(doc.created_at)} by {doc.created_by}</Text>
      </Stack>
      {canDelete && (
        <Tooltip label="Remove: pitches stop citing it">
          <ActionIcon variant="subtle" color="red" loading={remove.isPending} onClick={() => remove.mutate()} aria-label={`Remove ${doc.title}`}>
            <IconTrash size={16} />
          </ActionIcon>
        </Tooltip>
      )}
    </Group>
  );
}
