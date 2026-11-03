import { type AgencyProfile, LEAD_KINDS, type LeadKind, type ProfileRecord } from "@gigscout/api-client";
import { KIND_LABELS } from "@gigscout/viz";
import { Button, Checkbox, Group, Modal, NumberInput, SimpleGrid, Stack, TagsInput, Textarea, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, messageOf } from "../../lib/api";

const EMPTY: AgencyProfile = {
  name: "",
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

interface ProfileEditorProps {
  profile: ProfileRecord | null;
  opened: boolean;
  onClose: () => void;
}

export function ProfileEditor({ profile, opened, onClose }: ProfileEditorProps) {
  const queryClient = useQueryClient();
  const form = useForm<AgencyProfile>({
    initialValues: EMPTY,
    validate: {
      name: (v) => (v.trim() ? null : "Name your agency"),
      skills: (v) => (v.length ? null : "Add at least one technology you deliver in"),
      kinds: (v) => (v.length ? null : "Pick at least one lead kind"),
    },
  });

  useEffect(() => {
    if (!opened) return;
    form.setValues(profile ? { ...EMPTY, ...profile.data } : EMPTY);
    form.resetDirty();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens
  }, [opened, profile]);

  const save = useMutation({
    mutationFn: (data: AgencyProfile) => (profile ? api.profiles.update(profile.id, data) : api.profiles.create(data)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
      notifications.show({ color: "signal", message: profile ? "Profile saved" : "Profile created" });
      onClose();
    },
    onError: (error) => notifications.show({ color: "red", title: "Could not save", message: messageOf(error) }),
  });

  const tags = (field: keyof AgencyProfile, label: string, placeholder: string, description?: string) => (
    <TagsInput label={label} placeholder={placeholder} description={description} clearable {...form.getInputProps(field)} />
  );

  return (
    <Modal opened={opened} onClose={onClose} size="xl" title={<span className="gs-eyebrow">{profile ? "Edit agency profile" : "New agency profile"}</span>}>
      <form onSubmit={form.onSubmit((values) => save.mutate({ ...values, name: values.name.trim() }))}>
        <Stack gap="md">
          <TextInput label="Agency name" placeholder="Acme Software Studio" {...form.getInputProps("name")} />
          <Textarea label="Pitch" description="Two or three sentences on what you build and for whom" autosize minRows={2} maxLength={2000} {...form.getInputProps("pitch")} />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            {tags("services", "Services", "web app development…")}
            {tags("skills", "Delivery stack", "react, django…", "Required. Press Enter after each")}
            {tags("keywords", "Search keywords", "saas mvp…", "Seed the agents' searches")}
            {tags("industries", "Industries", "fintech…")}
            {tags("exclude", "Never show leads about", "wordpress, unpaid…")}
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
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={save.isPending}>{profile ? "Save profile" : "Create profile"}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
