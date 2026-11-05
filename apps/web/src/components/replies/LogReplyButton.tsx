import { Button, Group, Popover, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { api, messageOf } from "../../lib/api";
import { INTENT_META } from "./intents";

interface LogReplyButtonProps {
  outreachId: number;
  isEmail: boolean;
  onDone: () => void;
}

/** Paste in a client's reply that came another way (a marketplace message, a call note): the agents read it,
 * move the lead, and draft the answer. */
export function LogReplyButton({ outreachId, isEmail, onDone }: LogReplyButtonProps) {
  const [opened, setOpened] = useState(false);
  const [body, setBody] = useState("");
  const [from, setFrom] = useState("");
  const log = useMutation({
    mutationFn: () => api.replies.paste(outreachId, body, from.trim() || undefined),
    onSuccess: (r) => {
      setOpened(false);
      setBody("");
      const meta = INTENT_META[r.intent];
      notifications.show({ color: meta.color, title: meta.label, message: r.answer_id ? `${r.summary} An answer is waiting in Inbox.` : r.summary });
      onDone();
    },
    onError: (e) => notifications.show({ color: "red", title: "Reply not logged", message: messageOf(e) }),
  });
  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-end" width={340} withArrow trapFocus>
      <Popover.Target>
        <Button size="compact-xs" variant="subtle" onClick={() => setOpened((o) => !o)}>Log a reply</Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="xs">
          <Text size="xs">Paste what the client wrote. The agents read it, move the lead, and draft your answer.</Text>
          <Textarea size="xs" autosize minRows={4} maxRows={10} maxLength={20_000} value={body}
            placeholder="Thanks, this looks interesting. Could we do a call on Thursday?" onChange={(e) => setBody(e.currentTarget.value)} />
          {!isEmail && (
            <TextInput size="xs" label="Their email (optional)" description="So the answer can go by email" maxLength={254}
              value={from} onChange={(e) => setFrom(e.currentTarget.value)} />
          )}
          <Group justify="flex-end">
            <Button size="xs" loading={log.isPending} disabled={body.trim().length < 2} onClick={() => log.mutate()}>Read it</Button>
          </Group>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
