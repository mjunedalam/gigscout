import type { HoodStep } from "@gigscout/api-client";
import { IconBrain, IconDatabase, IconTool, IconWorldSearch } from "@tabler/icons-react";
import type { ReactNode } from "react";

export const OP_ICON: Record<HoodStep["op"], ReactNode> = {
  llm: <IconBrain size={14} />,
  tool: <IconTool size={14} />,
  fetch: <IconWorldSearch size={14} />,
  memory: <IconDatabase size={14} />,
};
export const OP_LABEL: Record<HoodStep["op"], string> = { llm: "AI call", tool: "tool", fetch: "source search", memory: "memory search" };
