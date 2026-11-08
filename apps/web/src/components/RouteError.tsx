import { Button, Code, Group, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconAlertTriangle, IconArrowLeft, IconRefresh } from "@tabler/icons-react";
import { isRouteErrorResponse, Link, useRouteError } from "react-router";

function messageFrom(error: unknown): string {
  if (isRouteErrorResponse(error)) return `${error.status} ${error.statusText}`;
  if (error instanceof Error) return error.message;
  return "Something unexpected went wrong.";
}

interface RouteErrorViewProps {
  message: string;
}

export function RouteErrorView({ message }: RouteErrorViewProps) {
  return (
    <Stack align="center" justify="center" gap="md" mih="60vh" ta="center" className="gs-rise" px="md">
      <ThemeIcon size={64} radius="xl" variant="light" color="red">
        <IconAlertTriangle size={30} />
      </ThemeIcon>
      <span className="gs-eyebrow">Something broke</span>
      <Title order={2} className="gs-display">
        This screen hit a snag
      </Title>
      <Text c="var(--gs-text-muted)" maw={460} size="sm">
        The rest of GigScout is fine and nothing was lost. Reload to try again, or head back to the command center.
      </Text>
      <Code block maw={560} style={{ whiteSpace: "pre-wrap", textAlign: "left" }}>
        {message}
      </Code>
      <Group gap="sm">
        <Button leftSection={<IconRefresh size={16} />} onClick={() => window.location.reload()}>
          Reload
        </Button>
        <Button component={Link} to="/" variant="light" leftSection={<IconArrowLeft size={16} />}>
          Back to command center
        </Button>
      </Group>
    </Stack>
  );
}

/** Router errorElement: a failing screen shows this inside the app shell instead of a blank developer page. */
export function RouteError() {
  const error = useRouteError();
  return <RouteErrorView message={messageFrom(error)} />;
}
