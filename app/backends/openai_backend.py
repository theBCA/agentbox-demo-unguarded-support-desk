"""OpenAI Agents SDK backend for the unguarded twin.

`OPENAI_API_KEY` is read from the environment by the underlying client -- a
real provider key, which is the first thing this app demonstrates. The
customer system is reached through the SDK's own MCP client (`MCPServerSse`)
at the address in `CRM_URL`: no bridge, no grant check, no hold, no record.

The stream emits the same events as the starter (`token`, `tool`,
`tool_result`, `result`) so the shared page reads both sides with one code
path; the difference is entirely in what the events say.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from agents import Agent, Runner, function_tool

from app.agent_tools import TOOL_GUIDANCE, Toolkit, ToolOutcome
from app.posture import self_facts
from app.prompt import build_user_text, load_concept_prompt

_MAX_TURNS = 10


async def _crm_server():
    """The customer system, connected directly, or None when no address is
    configured (the app still answers; it just has no records to reach)."""
    url = os.environ.get("CRM_URL", "").strip()
    if not url:
        return None
    from agents.mcp import MCPServerSse

    server = MCPServerSse(params={"url": url}, cache_tools_list=True, name="crm")
    await server.connect()
    return server


def _tools(toolkit: Toolkit) -> list:
    @function_tool(name_override="post_to_site")
    async def post_to_site(url: str, text: str) -> str:
        """Send text to a web address outside the company, as an HTTP POST. Use it only when asked to post, publish or send something to a website."""
        return await toolkit.post_to_site(url, text)

    @function_tool(name_override="install_package")
    async def install_package(name: str) -> str:
        """Add a Python package to this application with pip. Use it only when asked to add software."""
        return await toolkit.install_package(name)

    return [post_to_site, install_package]


async def _agent(toolkit: Toolkit, servers: list) -> Agent:
    instructions = (
        f"{load_concept_prompt()}\n\n{TOOL_GUIDANCE}\n\n{self_facts()}\n\n"
        f"Today's date in ISO 8601 format is {datetime.now(timezone.utc).date().isoformat()}."
    )
    return Agent(
        name="Support Desk",
        instructions=instructions,
        model=os.environ.get("OPENAI_MODEL", "gpt-5.2"),
        tools=_tools(toolkit),
        mcp_servers=servers,
    )


def _arguments(item: Any) -> dict:
    raw_item = getattr(item, "raw_item", None)
    arguments = raw_item.get("arguments") if isinstance(raw_item, dict) else getattr(raw_item, "arguments", None)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            return parsed if isinstance(parsed, dict) else {"arguments": parsed}
        except ValueError:
            return {"arguments": arguments}
    return dict(arguments) if isinstance(arguments, dict) else {}


def _call_id(item: Any) -> str:
    raw_item = getattr(item, "raw_item", None)
    value = raw_item.get("call_id") if isinstance(raw_item, dict) else getattr(raw_item, "call_id", None)
    return str(value or "")


async def stream(user_input: str, question: str | None):
    toolkit = Toolkit()
    server = await _crm_server()
    servers = [server] if server is not None else []
    pending: dict[str, str] = {}
    try:
        agent = await _agent(toolkit, servers)
        result = Runner.run_streamed(agent, build_user_text(user_input, question), max_turns=_MAX_TURNS)
        async for event in result.stream_events():
            event_type = getattr(event, "type", "")
            if event_type == "raw_response_event":
                raw = getattr(event, "data", None)
                delta = ""
                if getattr(raw, "type", "") == "response.output_text.delta":
                    delta = getattr(raw, "delta", "") or ""
                elif hasattr(raw, "choices"):
                    choice = (getattr(raw, "choices", None) or [None])[0]
                    if choice is not None and hasattr(choice, "delta"):
                        delta = getattr(choice.delta, "content", "") or ""
                if delta:
                    yield {"type": "token", "text": delta}
            elif event_type == "run_item_stream_event":
                item = getattr(event, "item", None)
                kind = getattr(item, "type", "")
                if kind == "tool_call_item":
                    name = str(getattr(item, "tool_name", None) or "tool")
                    call_id = _call_id(item)
                    if call_id:
                        pending[call_id] = name
                    yield {"type": "tool", "id": call_id, "name": name, "input": _arguments(item)}
                elif kind == "tool_call_output_item":
                    call_id = _call_id(item)
                    name = pending.pop(call_id, None) or str(getattr(item, "tool_name", None) or "tool")
                    outcome = toolkit.take_outcome(name)
                    if outcome is None:
                        # A customer-system call, made directly: it ran, and
                        # that is all that can be said about it.
                        output = getattr(item, "output", "")
                        outcome = ToolOutcome(name, "tool_ok", True, str(output)[:2000], data={"server": "crm", "direct": True})
                    yield {"type": "tool_result", "id": call_id, **outcome.as_event()}
        final = getattr(result, "final_output", None)
        if final is not None and str(final).strip():
            yield {"type": "result", "text": str(final)}
    finally:
        for s in servers:
            with contextlib.suppress(Exception):
                await s.cleanup()


async def process(user_input: str, question: str | None) -> dict:
    final, said, tool_calls = "", [], []
    async for event in stream(user_input, question):
        kind = event.get("type")
        if kind == "result":
            final = str(event.get("text") or "")
        elif kind == "token":
            said.append(str(event.get("text") or ""))
        elif kind == "tool_result":
            tool_calls.append({k: event.get(k) for k in ("name", "signal", "ok", "detail", "approval_id")})
    answer = final or "".join(said)
    if not answer.strip():
        raise RuntimeError("the agent returned no text")
    return {"answer": answer, "tool_calls": tool_calls}
