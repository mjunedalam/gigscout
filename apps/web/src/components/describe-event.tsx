import type { LiveEvent } from "@gigscout/api-client";
import {
  IconBolt,
  IconCalendarOff,
  IconCircleCheck,
  IconCircleX,
  IconClockHour4,
  IconMail,
  IconMailbox,
  IconPlayerPlay,
  IconPlugConnected,
  IconPlugConnectedX,
  IconTag,
} from "@tabler/icons-react";
import type { ReactNode } from "react";

interface Described {
  icon: ReactNode;
  color: string;
  text: string;
}

export function describeEvent(event: LiveEvent): Described {
  const d = event.data as Record<string, string | number | null>;
  switch (event.type) {
    case "run.queued":
      return { icon: <IconClockHour4 size={14} />, color: "gray", text: `Run queued for ${d.profile_name}` };
    case "run.started":
      return { icon: <IconPlayerPlay size={14} />, color: "blue", text: `Agents started scouting for ${d.profile_name}` };
    case "run.finished":
      if (d.status === "succeeded") return { icon: <IconCircleCheck size={14} />, color: "signal", text: `Run done: ${d.new_count} new, ${d.match_count} qualified` };
      if (d.status === "cancelled") return { icon: <IconCircleX size={14} />, color: "gray", text: `Run stopped for ${d.profile_name}` };
      return { icon: <IconCircleX size={14} />, color: "red", text: `Run failed for ${d.profile_name}` };
    case "run.stopping":
      return { icon: <IconCircleX size={14} />, color: "gray", text: "Stopping the run at the agents' next step" };
    case "run.cancelled":
      return { icon: <IconCircleX size={14} />, color: "gray", text: "Queued run cancelled" };
    case "lead.inbound":
      return { icon: <IconMailbox size={14} />, color: "pink", text: `Inbound: ${d.title}` };
    case "lead.updated":
      return { icon: <IconTag size={14} />, color: "violet", text: `${d.by} moved "${d.title}"${d.status ? ` → ${d.status}` : ""}` };
    case "lead.assigned":
      return { icon: <IconTag size={14} />, color: "blue", text: `${d.by} gave "${d.title}" to ${d.to}` };
    case "source.added":
      return { icon: <IconPlugConnected size={14} />, color: "teal", text: `Website connected: ${d.name}` };
    case "source.blocked":
      return { icon: <IconPlugConnectedX size={14} />, color: "orange", text: `${d.name} now blocks automated access` };
    case "pitch.drafted":
      return { icon: <IconMail size={14} />, color: "violet", text: `${d.count} ${d.follow_up ? "follow-up" : "pitch"}${d.count === 1 ? "" : "es"} drafted, waiting for approval` };
    case "reply.received":
      return { icon: <IconMail size={14} />, color: "teal", text: `Reply on ${d.title}: ${d.summary}` };
    case "digest.sent":
      return { icon: <IconMail size={14} />, color: "signal", text: `Daily digest: ${d.count} leads sent` };
    case "schedule.skipped":
      return { icon: <IconCalendarOff size={14} />, color: "yellow", text: `Schedule "${d.name}" skipped (run in progress)` };
    default:
      return { icon: <IconBolt size={14} />, color: "gray", text: event.type };
  }
}
