import { LEAD_KINDS, LEAD_STATUSES, type LeadKind, type LeadQuery, type LeadStatus } from "@gigscout/api-client";
import { KIND_LABELS } from "@gigscout/viz";
import {
  Alert,
  Group,
  MultiSelect,
  Pagination,
  SegmentedControl,
  Select,
  Skeleton,
  Slider,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconLayoutKanban, IconSearch, IconTable } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { LeadDrawer } from "../components/LeadDrawer";
import { PageHeader, Panel } from "../components/layout-bits";
import { PipelineBoard } from "../components/leads/PipelineBoard";
import { LeadTable } from "../components/leads/LeadTable";
import { api, messageOf } from "../lib/api";

const PAGE_SIZE = 25;
const BOARD_SIZE = 200;

/** Filters live in the URL, so a filtered view can be bookmarked or shared with the team. */
function useLeadFilters() {
  const [params, setParams] = useSearchParams();
  const set = (key: string, value: string | string[] | null) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete(key);
        if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
        else if (value) next.set(key, value);
        if (key !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );
  return {
    view: (params.get("view") ?? "table") as "table" | "board",
    q: params.get("q") ?? "",
    kind: params.getAll("kind") as LeadKind[],
    status: params.getAll("status") as LeadStatus[],
    sort: (params.get("sort") ?? "score") as NonNullable<LeadQuery["sort"]>,
    minScore: Number(params.get("min") ?? 0),
    page: Number(params.get("page") ?? 1),
    open: params.get("lead"),
    set,
  };
}

export default function LeadsPage() {
  const f = useLeadFilters();
  const [search, setSearch] = useState(f.q);
  const [debounced] = useDebouncedValue(search, 350);
  useEffect(() => {
    if (debounced !== f.q) f.set("q", debounced || null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the debounced text
  }, [debounced]);

  const query: LeadQuery = {
    q: f.q || undefined,
    kind: f.kind,
    status: f.view === "board" ? [] : f.status,
    sort: f.sort,
    min_score: f.minScore > 0 ? f.minScore / 100 : undefined,
    page: f.view === "board" ? 1 : f.page,
    page_size: f.view === "board" ? BOARD_SIZE : PAGE_SIZE,
  };
  const leads = useQuery({
    queryKey: ["leads", "list", query],
    queryFn: () => api.leads.list(query),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Leads"
        description="Search by meaning, filter by kind and stage, and move leads through your pipeline."
        actions={
          <SegmentedControl
            value={f.view}
            onChange={(v) => f.set("view", v === "table" ? null : v)}
            data={[
              { value: "table", label: <Group gap={6} wrap="nowrap"><IconTable size={16} />Table</Group> },
              { value: "board", label: <Group gap={6} wrap="nowrap"><IconLayoutKanban size={16} />Pipeline</Group> },
            ]}
          />
        }
      />

      <Panel padding={16} className="gs-rise">
        <Group gap="md" align="flex-end" wrap="wrap">
          <TextInput
            flex="1 1 260px"
            label="Search by meaning"
            placeholder="e.g. clinic booking app in React Native"
            leftSection={<IconSearch size={16} />}
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
          />
          <MultiSelect
            w={220}
            label="Kind"
            placeholder="All kinds"
            data={LEAD_KINDS.map((k) => ({ value: k, label: KIND_LABELS[k] }))}
            value={f.kind}
            onChange={(v) => f.set("kind", v)}
            clearable
          />
          {f.view === "table" && (
            <MultiSelect
              w={200}
              label="Stage"
              placeholder="All stages"
              data={[...LEAD_STATUSES]}
              value={f.status}
              onChange={(v) => f.set("status", v)}
              clearable
            />
          )}
          <Select
            w={150}
            label="Sort"
            data={[
              { value: "score", label: "Best score" },
              { value: "recent", label: "Newest" },
              { value: "budget", label: "Biggest budget" },
            ]}
            value={f.sort}
            onChange={(v) => f.set("sort", v === "score" ? null : v)}
            disabled={!!f.q}
            allowDeselect={false}
          />
          <Stack gap={4} w={180}>
            <Text size="sm" fw={500}>
              Min score <span className="gs-num">{f.minScore}</span>
            </Text>
            <Slider
              value={f.minScore}
              onChangeEnd={(v) => f.set("min", v ? String(v) : null)}
              step={5}
              label={null}
              aria-label="Minimum score"
            />
          </Stack>
        </Group>
      </Panel>

      <Stack mt="md" gap="md">
        {leads.isError && <Alert color="red">{messageOf(leads.error)}</Alert>}
        {leads.isPending && <Skeleton h={420} radius="lg" />}
        {leads.data && f.view === "table" && (
          <>
            <LeadTable items={leads.data.items} searching={!!f.q} onOpen={(id) => f.set("lead", id)} />
            <Group justify="space-between">
              <Text size="sm" c="var(--gs-text-muted)" className="gs-mono">
                {leads.data.total} leads
              </Text>
              <Pagination
                total={Math.max(1, Math.ceil(leads.data.total / PAGE_SIZE))}
                value={f.page}
                onChange={(p) => f.set("page", String(p))}
                size="sm"
              />
            </Group>
          </>
        )}
        {leads.data && f.view === "board" && <PipelineBoard items={leads.data.items} onOpen={(id) => f.set("lead", id)} />}
      </Stack>

      <LeadDrawer leadId={f.open} onClose={() => f.set("lead", null)} />
    </>
  );
}
