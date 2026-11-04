"""Under the hood: every model call and tool call an agent makes, recorded as `hood` activity for the UI.

A LangChain callback handler, so it sees the real traffic without changing the agents: the prompt the model was
given, what it answered (text or tool calls), how long it took and how many tokens it used; and for tools, the
arguments and the observation the agent read back. Contact details never reach prompts (see describe_client), so
nothing here needs extra redaction.
"""

import json
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from gigscout.activity import Activity

AGENT_NAMES = {
    "head": "Head of Sales", "prospector": "Prospector", "qualifier": "Qualifier", "writer": "Outreach Writer",
}
PURPOSE = {  # pipeline mode: what a model call is for, by the step it happens in
    "plan": "plan the searches", "qualify": "judge a lead", "write": "draft outreach", "report": "write the briefing",
}
DELEGATES = {
    "delegate_to_scout": "Prospector", "delegate_to_analyst": "Qualifier", "delegate_to_writer": "Outreach Writer",
}
TOOL_PHRASE = {  # what each tool does, in the words the UI shows
    "delegate_to_scout": "hand the work to the Prospector", "delegate_to_analyst": "hand the work to the Qualifier",
    "delegate_to_writer": "hand the work to the Outreach Writer", "check_progress": "check the team's progress",
    "list_sources": "list the lead sources", "search_source": "search a lead source",
    "search_progress": "check its search budget", "find_leads": "search memory for leads",
    "read_lead": "read a lead in full", "qualify_lead": "score a lead", "view_shortlist": "look at the shortlist",
    "submit_report": "submit the briefing",
}
MAX_MESSAGES = 6  # the system prompt plus the latest turns; earlier turns are summarised by count


class HoodRecorder(BaseCallbackHandler):
    """Turns model and tool callbacks into `hood` events. `agent` pins the role (team mode gives each agent its own
    recorder); without it the current run step decides (pipeline mode)."""

    raise_error = False  # a recording problem must never break a run

    def __init__(self, activity: Activity, agent: str | None = None) -> None:
        self._activity = activity
        self._agent = agent
        self._started: dict[UUID, tuple[float, dict[str, Any]]] = {}
        self._delegations: set[UUID] = set()  # while one runs, the worker's own recorder reports its steps

    def _skip(self) -> bool:
        return bool(self._delegations)

    def _who(self) -> str:
        return self._agent or self._activity.current_agent

    # --- model calls -------------------------------------------------------------------------------------------
    def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[BaseMessage]], *, run_id: UUID,
                            invocation_params: dict[str, Any] | None = None,
                            metadata: dict[str, Any] | None = None, **_: Any) -> None:
        if self._skip():
            return
        params = invocation_params or {}
        model = ((metadata or {}).get("ls_model_name") or params.get("model") or params.get("model_name")
                 or (serialized or {}).get("name") or "model")
        thread = messages[0] if messages else []
        shown = thread if len(thread) <= MAX_MESSAGES else [thread[0], *thread[-(MAX_MESSAGES - 1):]]
        self._started[run_id] = (time.monotonic(), {
            "model": str(model),
            "messages": [{"role": _role(m), "text": _message_text(m)} for m in shown],
            "earlier_messages": max(0, len(thread) - len(shown)),
        })

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **_: Any) -> None:
        started, info = self._started.pop(run_id, (None, {}))
        if started is None:
            return
        message = _first_message(response)
        calls = [{"tool": c.get("name"), "args": c.get("args")} for c in getattr(message, "tool_calls", None) or []]
        usage = getattr(message, "usage_metadata", None) or {}
        agent = self._who()
        purpose = None if self._agent else PURPOSE.get(self._activity.current_stage or "plan")
        if calls:
            plans = " and ".join(_plan(str(c["tool"]), c["args"]) for c in calls)
            title = f"{AGENT_NAMES.get(agent, agent)} decided to {plans}"
        elif purpose:
            title = f"{AGENT_NAMES.get(agent, agent)} asked the AI to {purpose}"
            busy = self._activity.busy_with(agent)
            if agent == "qualifier" and busy.startswith("checking "):
                title += f": {busy.removeprefix('checking ')}"
        else:
            title = f"{AGENT_NAMES.get(agent, agent)} thought and replied"
        self._activity.hood(
            agent, "llm", title, _ms(started), **info, reply=_text(message) if message else None,
            tool_calls=calls or None, tokens_in=usage.get("input_tokens"), tokens_out=usage.get("output_tokens"),
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **_: Any) -> None:
        started, info = self._started.pop(run_id, (None, {}))
        if started is not None:
            agent = self._who()
            self._activity.hood(agent, "llm", f"{AGENT_NAMES.get(agent, agent)}'s AI call failed", _ms(started),
                                **info, error=f"{type(error).__name__}: {error}")

    # --- tool calls --------------------------------------------------------------------------------------------
    def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID,
                      inputs: dict[str, Any] | None = None, **_: Any) -> None:
        if self._skip():
            return
        name = str((serialized or {}).get("name") or "tool")
        if name in DELEGATES:
            self._delegations.add(run_id)
        self._started[run_id] = (time.monotonic(), {"tool": name, "args": inputs if inputs else input_str})

    def on_tool_end(self, output: Any, *, run_id: UUID, **_: Any) -> None:
        self._delegations.discard(run_id)
        started, info = self._started.pop(run_id, (None, {}))
        if started is None:
            return
        agent, tool = self._who(), info.get("tool", "tool")
        who = AGENT_NAMES.get(agent, agent)
        title = (f"{who} handed the work to the {DELEGATES[tool]}" if tool in DELEGATES
                 else f"{who} used a tool to {_plan(tool, info.get('args'))}")
        self._activity.hood(agent, "tool", title, _ms(started), **info, result=_text(output))

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **_: Any) -> None:
        self._delegations.discard(run_id)
        started, info = self._started.pop(run_id, (None, {}))
        if started is not None:
            agent = self._who()
            self._activity.hood(agent, "tool", f"{AGENT_NAMES.get(agent, agent)}'s {info.get('tool')} failed",
                                _ms(started), **info, error=f"{type(error).__name__}: {error}")


def _plan(tool: str, args: Any) -> str:
    """What a tool call does, with its key arguments: "search remotive for 'django'"."""
    args = args if isinstance(args, dict) else {}
    if tool == "search_source" and args.get("source"):
        return f"search {args['source']} for '{args.get('query', '')}'"
    if tool == "find_leads" and args.get("query"):
        return f"search memory for '{args['query']}'"
    return TOOL_PHRASE.get(tool, f"use {tool}")


def _message_text(message: BaseMessage) -> str:
    """A turn's text; a turn that only called tools reads as those calls."""
    text = _text(message)
    calls = getattr(message, "tool_calls", None) or []
    if text.strip() or not calls:
        return text
    return "\n".join(f"→ {c.get('name')}({json.dumps(c.get('args'), ensure_ascii=False)[:300]})" for c in calls)


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _first_message(response: LLMResult) -> BaseMessage | None:
    for generations in response.generations:
        for generation in generations:
            message = getattr(generation, "message", None)
            if message is not None:
                return message
    return None


def _role(message: BaseMessage) -> str:
    return {"human": "user", "ai": "assistant"}.get(message.type, message.type)


def _text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)
