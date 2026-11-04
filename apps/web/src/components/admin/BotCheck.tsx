import { Badge, Button, Code, CopyButton, Group, Stack, Text } from "@mantine/core";
import { IconCopy, IconShieldCheck, IconShieldOff } from "@tabler/icons-react";

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js";

/** The website form's Cloudflare Turnstile state, and the snippet to paste into the company's own form. */
export function BotCheck({ on, siteKey }: { on: boolean; siteKey: string | null }) {
  if (!on) {
    return (
      <Group gap={6} mt="xs" wrap="nowrap">
        <IconShieldOff size={14} color="var(--gs-text-muted)" />
        <Text size="xs" c="var(--gs-text-muted)">
          No bot check. Set GIGSCOUT_TURNSTILE_SECRET_KEY in apps/api/.env to require Cloudflare Turnstile.
        </Text>
      </Group>
    );
  }
  const snippet = [
    `<script src="${SCRIPT}" async defer></script>`,
    "<!-- inside your <form>, just above the send button: -->",
    `<div class="cf-turnstile" data-sitekey="${siteKey ?? "YOUR_SITE_KEY"}"></div>`,
  ].join("\n");
  return (
    <Stack gap={4} mt="xs">
      <Group justify="space-between">
        <Badge size="sm" variant="light" color="signal" leftSection={<IconShieldCheck size={12} />}>
          Bot check on · Cloudflare Turnstile
        </Badge>
        <CopyButton value={snippet}>
          {({ copied, copy }) => (
            <Button size="compact-xs" variant="subtle" leftSection={<IconCopy size={12} />} onClick={copy}>
              {copied ? "Copied" : "Copy snippet"}
            </Button>
          )}
        </CopyButton>
      </Group>
      <Text size="xs" c="var(--gs-text-muted)">
        Submissions without a passed check are refused. Add this to your website's form:
      </Text>
      <Code block style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{snippet}</Code>
      {!siteKey && <Text size="xs" c="orange">Set GIGSCOUT_TURNSTILE_SITE_KEY to fill in your site key.</Text>}
    </Stack>
  );
}
