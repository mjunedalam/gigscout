import { type AgencyProfile, LEAD_KINDS, type LeadKind, type ProfileRecord, type ProfileTemplate } from "@gigscout/api-client";
import { KIND_LABELS } from "@gigscout/viz";
import {
  Alert, Autocomplete, Button, Checkbox, Divider, Group, Modal, MultiSelect, NumberInput, SimpleGrid, Stack, Switch,
  TagsInput, Text, Textarea, TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconPlayerPlay, IconSparkles } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { useAuth } from "../../lib/auth";
import { api, messageOf } from "../../lib/api";

const EMPTY: AgencyProfile = {
  name: "",
  company_type: "",
  pitch: "",
  services: [],
  skills: [],
  keywords: [],
  industries: [],
  exclude: [],
  min_budget_usd: null,
  target_countries: [],
  kinds: [...LEAD_KINDS],
  sources: null,
};
const SUGGESTED_FIELDS = ["services", "skills", "keywords", "exclude", "industries"] as const;

interface ProfileEditorProps {
  profile: ProfileRecord | null;
  opened: boolean;
  onClose: () => void;
}

/** Any kind of company describes itself here; the agents then prospect for exactly that business. */
export function ProfileEditor({ profile, opened, onClose }: ProfileEditorProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [suggestNote, setSuggestNote] = useState<string | null>(null);
  const templates = useQuery({ queryKey: ["profiles", "templates"], queryFn: api.profiles.templates, enabled: opened });
  const sources = useQuery({ queryKey: ["admin", "sources"], queryFn: api.admin.sources, enabled: opened && isAdmin });
  const form = useForm<AgencyProfile>({
    initialValues: EMPTY,
    validate: {
      name: (v) => (v.trim() ? null : "Name your company"),
      company_type: (v) => (v.trim() ? null : "What kind of company is it?"),
      services: (_v, values) =>
        values.services.length || values.skills.length || values.keywords.length
          ? null : "Add at least one service, capability or search keyword (or use Suggest with AI)",
      kinds: (v) => (v.length ? null : "Pick at least one lead kind"),
    },
  });

  useEffect(() => {
    if (!opened) return;
    // profiles saved before company types existed are software agencies
    form.setValues(profile ? { ...EMPTY, ...profile.data, company_type: profile.data.company_type || "Software agency" } : EMPTY);
    form.resetDirty();
    setSuggestNote(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens
  }, [opened, profile]);

  /** Picking a known company type on a fresh profile prefills it from the template. */
  const applyTemplate = (type: string) => {
    const t = templates.data?.find((x) => x.company_type === type);
    const untouched = SUGGESTED_FIELDS.every((f) => form.values[f].length === 0);
    if (!t || !untouched) return;
    fill(t);
    setSuggestNote(`Prefilled for a ${t.company_type.toLowerCase()}. Edit anything, or use Suggest with AI for your own words.`);
  };
  const fill = (s: Pick<ProfileTemplate, "services" | "skills" | "keywords" | "exclude"> & { industries?: string[]; kinds?: LeadKind[] }) => {
    form.setValues({
      services: s.services, skills: s.skills, keywords: s.keywords, exclude: s.exclude,
      ...(s.industries?.length ? { industries: s.industries } : {}),
      ...(s.kinds ? { kinds: s.kinds } : {}),
    });
  };

  const suggest = useMutation({
    mutationFn: () => api.profiles.suggest(form.values.company_type.trim(), form.values.pitch.trim()),
    onSuccess: (s) => {
      if (s.source === "none") {
        setSuggestNote("No suggestion for this kind of company yet: add a few services and search keywords yourself.");
        return;
      }
      fill(s);
      setSuggestNote(s.source === "ai"
        ? "Suggested by the AI from your description. Review and edit before saving."
        : "The AI model is not available, so this is the closest template. Review and edit before saving.");
    },
    onError: (error) => notifications.show({ color: "red", title: "Could not suggest", message: messageOf(error) }),
  });

  const save = useMutation({
    mutationFn: async ({ data, scout }: { data: AgencyProfile; scout: boolean }) => {
      const saved = profile ? await api.profiles.update(profile.id, data) : await api.profiles.create(data);
      if (scout) await api.runs.start(saved.id, "auto");
      return { saved, scout };
    },
    onSuccess: ({ saved, scout }) => {
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      notifications.show({
        color: "signal",
        title: profile ? "Profile saved" : "Profile created",
        message: scout ? `The agents are scouting for ${saved.name}.` : undefined,
      });
      onClose();
      if (scout) navigate("/cockpit");
    },
    onError: (error) => notifications.show({ color: "red", title: "Could not save", message: messageOf(error) }),
  });
  const submit = (scout: boolean) =>
    form.onSubmit((values) => save.mutate({ data: { ...values, name: values.name.trim(), company_type: values.company_type.trim() }, scout }));

  const tags = (field: keyof AgencyProfile, label: string, placeholder: string, description?: string) => (
    <TagsInput label={label} placeholder={placeholder} description={description} clearable {...form.getInputProps(field)} />
  );
  const pullSources = (sources.data ?? []).filter((s) => s.channel === "pull" && s.enabled);
  const searchAll = form.values.sources === null;

  return (
    <Modal opened={opened} onClose={onClose} size="xl" title={<span className="gs-eyebrow">{profile ? "Edit company profile" : "New company profile"}</span>}>
      <form onSubmit={submit(false)}>
        <Stack gap="md">
          <Divider label="Your company" labelPosition="left" />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Autocomplete
              label="Company type"
              description="Pick one or type your own"
              placeholder="Marketing agency, law firm, recruiter…"
              data={templates.data?.map((t) => t.company_type) ?? []}
              {...form.getInputProps("company_type")}
              onOptionSubmit={applyTemplate}
            />
            <TextInput label="Company name" placeholder="Bright Lane Marketing" {...form.getInputProps("name")} />
          </SimpleGrid>
          <Textarea label="What you do" description="Two or three sentences on what you sell and to whom"
            autosize minRows={2} maxLength={2000} {...form.getInputProps("pitch")} />
          <Group justify="space-between" align="center" wrap="wrap">
            <Text size="xs" c="var(--gs-text-muted)">Describe your company, then let the AI fill in the rest.</Text>
            <Button variant="light" leftSection={<IconSparkles size={16} />} loading={suggest.isPending}
              disabled={form.values.company_type.trim().length < 2} onClick={() => suggest.mutate()}>
              Suggest with AI
            </Button>
          </Group>
          {suggestNote && <Alert variant="light" color="signal" withCloseButton onClose={() => setSuggestNote(null)}>{suggestNote}</Alert>}

          <Divider label="What you sell" labelPosition="left" />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            {tags("services", "Services", "seo, contract drafting…", "What clients buy from you")}
            {tags("skills", "Capabilities", "google ads, gdpr, react…", "What you are good at (optional)")}
            {tags("keywords", "Search keywords", "ppc, legal counsel…", "Short phrases the agents search for")}
            {tags("industries", "Client industries", "ecommerce, healthcare…")}
            {tags("exclude", "Never show leads about", "unpaid, spec work…")}
            {tags("target_countries", "Target client countries", "United States…", "Empty = worldwide")}
          </SimpleGrid>
          <NumberInput
            label="Smallest deal worth your time (USD)"
            min={0}
            step={500}
            thousandSeparator=","
            prefix="$"
            value={form.values.min_budget_usd ?? ""}
            onChange={(v) => form.setFieldValue("min_budget_usd", typeof v === "number" ? v : null)}
          />
          <Checkbox.Group label="Lead kinds to pursue" {...form.getInputProps("kinds")}>
            <Group mt="xs">
              {LEAD_KINDS.map((k: LeadKind) => (
                <Checkbox key={k} value={k} label={KIND_LABELS[k]} />
              ))}
            </Group>
          </Checkbox.Group>

          <Divider label="Where to look" labelPosition="left" />
          <Switch
            label="Search every connected source"
            description="Turn off to choose. Add your industry's websites in Admin › Connectors."
            checked={searchAll}
            onChange={(e) => form.setFieldValue("sources", e.currentTarget.checked ? null : pullSources.map((s) => s.name))}
          />
          {!searchAll && (
            <MultiSelect
              label="Sources for this company"
              placeholder="Pick sources"
              data={pullSources.map((s) => ({ value: s.name, label: s.label ?? s.name }))}
              value={form.values.sources ?? []}
              onChange={(v) => form.setFieldValue("sources", v)}
              searchable
            />
          )}

          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant={profile ? "filled" : "default"} loading={save.isPending && !save.variables?.scout}>
              {profile ? "Save profile" : "Create profile"}
            </Button>
            {!profile && (
              <Button leftSection={<IconPlayerPlay size={16} />} loading={save.isPending && save.variables?.scout}
                onClick={() => submit(true)()}>
                Create &amp; start scouting
              </Button>
            )}
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
