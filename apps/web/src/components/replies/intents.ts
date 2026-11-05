import type { ReplyIntent } from "@gigscout/api-client";

/** How each kind of reply is named and coloured everywhere (badges, filters, notifications). */
export const INTENT_META: Record<ReplyIntent, { label: string; color: string; hint: string }> = {
  meeting: { label: "Wants a call", color: "teal", hint: "The lead moved to proposal. Propose times." },
  interested: { label: "Interested", color: "signal", hint: "Keep the momentum: answer today." },
  question: { label: "Question", color: "blue", hint: "They need an answer before deciding." },
  not_now: { label: "Not now", color: "yellow", hint: "Set a follow-up date on the lead." },
  not_interested: { label: "Not interested", color: "red", hint: "The lead was marked lost. No answer drafted." },
  out_of_office: { label: "Auto-reply", color: "gray", hint: "An out-of-office: nothing to answer." },
  unsubscribe: { label: "Unsubscribe", color: "red", hint: "Do not contact again. The lead was marked lost." },
};
