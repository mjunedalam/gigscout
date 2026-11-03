import { KIND_COLORS, KIND_LABELS } from "@gigscout/viz";
import { Alert, Box, Button, Group, PasswordInput, SimpleGrid, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertCircle, IconArrowRight } from "@tabler/icons-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { messageOf } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: {
      email: (v) => (v.trim().length ? null : "Enter your email or username"),
      password: (v) => (v.length ? null : "Enter your password"),
    },
  });

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={from} replace />;

  const submit = form.onSubmit(async ({ email, password }) => {
    setError(null);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (e) {
      setError(messageOf(e));
    }
  });

  return (
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing={0} mih="100vh">
      <Box visibleFrom="md" className="gs-panel-hero" style={{ position: "relative", overflow: "hidden" }} p={56}>
        <Orbit />
        <Stack justify="space-between" h="100%" style={{ position: "relative" }}>
          <Text className="gs-display" fw={600} fz={22}>
            GigScout
          </Text>
          <Stack gap="md" maw={480}>
            <span className="gs-eyebrow">Agency lead command center</span>
            <Title order={1} className="gs-display" fz={54} lh={1}>
              Your next client is already posting. Get there first.
            </Title>
            <Text c="var(--gs-text-muted)">
              Agents scan marketplaces, hiring signals and your Google Ads enquiries, qualify every lead, and
              hand your sales team the opener.
            </Text>
          </Stack>
          <Group gap="lg">
            {(Object.keys(KIND_COLORS) as (keyof typeof KIND_COLORS)[]).map((k) => (
              <Group key={k} gap={6}>
                <span className="gs-dot" style={{ background: KIND_COLORS[k] }} />
                <Text size="xs" c="var(--gs-text-muted)">
                  {KIND_LABELS[k]}
                </Text>
              </Group>
            ))}
          </Group>
        </Stack>
      </Box>

      <Stack justify="center" align="center" p="xl">
        <Box component="form" onSubmit={submit} w="100%" maw={380} className="gs-rise" noValidate>
          <Stack gap="lg">
            <Stack gap={4}>
              <span className="gs-eyebrow">Welcome back</span>
              <Title order={2} className="gs-display">
                Sign in
              </Title>
            </Stack>
            {error && (
              <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />}>
                {error}
              </Alert>
            )}
            <TextInput label="Email or username" autoComplete="username" placeholder="you@agency.com" size="md" {...form.getInputProps("email")} />
            <PasswordInput label="Password" autoComplete="current-password" size="md" {...form.getInputProps("password")} />
            <Button type="submit" size="md" rightSection={<IconArrowRight size={18} />} loading={form.submitting}>
              Enter the command center
            </Button>
            <Text size="xs" c="var(--gs-text-muted)">
              No account? An admin can invite you, or create the first admin with{" "}
              <code className="gs-mono">gigscout create-admin</code>.
            </Text>
          </Stack>
        </Box>
      </Stack>
    </SimpleGrid>
  );
}

/** Decorative orbiting rings in the lead-kind colours (CSS transforms only). */
function Orbit() {
  const rings = [
    { size: 520, color: KIND_COLORS.project, duration: 38 },
    { size: 380, color: KIND_COLORS.contract, duration: 28 },
    { size: 250, color: KIND_COLORS.hiring, duration: 20 },
    { size: 140, color: KIND_COLORS.inbound, duration: 14 },
  ];
  return (
    <Box aria-hidden style={{ position: "absolute", right: -120, top: "50%", transform: "translateY(-50%)", opacity: 0.55 }}>
      {rings.map((r) => (
        <Box
          key={r.size}
          style={{
            position: "absolute",
            width: r.size,
            height: r.size,
            left: -r.size / 2,
            top: -r.size / 2,
            borderRadius: "50%",
            border: `1px solid color-mix(in srgb, ${r.color} 45%, transparent)`,
            animation: `gs-spin ${r.duration}s linear infinite`,
          }}
        >
          <span
            className="gs-dot"
            style={{ position: "absolute", top: -4, left: "50%", width: 9, height: 9, background: r.color, boxShadow: `0 0 18px ${r.color}` }}
          />
        </Box>
      ))}
    </Box>
  );
}
