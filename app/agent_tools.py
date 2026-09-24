"""The unguarded agent's two loose tools, and the record of what they did.

The starter's toolkit routes every action through a control and reports the
control's verdict. This one has the same two fixed tools -- `post_to_site` and
`install_package` -- and the same signal vocabulary, but no control is
consulted: the post goes straight out (`proxied: False`), the install reaches
pip (`governed: False`). The customer system is not in here at all: the agent
is handed the CRM server's address and the SDK calls it directly, so those
calls arrive in the stream as plain tool outputs and are reported `tool_ok` --
no hold, no refusal, no record, which is the whole of the comparison.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app import egress

POST_TO_SITE = "post_to_site"
INSTALL_PACKAGE = "install_package"

TOOL_GUIDANCE = (
    "You have tools. The ones named after the company's systems read or change "
    "real records; post_to_site sends text to a website; install_package adds "
    "software to this application. Use a tool when the request needs one and "
    "not otherwise, and say in one short sentence what you are about to do "
    "before you call it. Read every tool result before answering and relay it "
    "plainly. Never describe a result a tool did not return."
)

_MAX_DETAIL_CHARS = 2_000


@dataclass(frozen=True)
class ToolOutcome:
    name: str
    signal: str
    ok: bool
    detail: str
    approval_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def as_event(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "signal": self.signal,
            "ok": self.ok,
            "detail": self.detail[:_MAX_DETAIL_CHARS],
            "approval_id": self.approval_id,
            "data": dict(self.data),
        }


class Toolkit:
    """The two fixed tools of one request, and their outcomes in call order."""

    def __init__(self) -> None:
        self._outcomes: dict[str, deque[ToolOutcome]] = defaultdict(deque)

    def take_outcome(self, name: str) -> ToolOutcome | None:
        queue = self._outcomes.get(name)
        return queue.popleft() if queue else None

    def _record(self, outcome: ToolOutcome) -> str:
        self._outcomes[outcome.name].append(outcome)
        return outcome.detail

    async def post_to_site(self, url: str, text: str) -> str:
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return self._record(
                ToolOutcome(POST_TO_SITE, "failed", False, "url must be a full http:// or https:// address")
            )
        host = parts.hostname
        data: dict[str, Any] = {"host": host, "port": parts.port or (443 if parts.scheme == "https" else 80), "proxied": False}
        try:
            sent = await egress.post(url, text)
        except Exception as exc:  # noqa: BLE001 - reported to the model
            return self._record(ToolOutcome(POST_TO_SITE, "failed", False, f"could not send to {host}: {exc}", data=data))
        data["status"] = sent.get("status")
        return self._record(
            ToolOutcome(
                POST_TO_SITE,
                "egress_ok",
                True,
                f"Sent to {host}; it answered HTTP {sent.get('status')}. This application has no outbound gate, so the request went straight out.",
                data=data,
            )
        )

    async def install_package(self, name: str) -> str:
        name = name.strip()
        data: dict[str, Any] = {"package": name, "verdict": "none", "governed": False}
        if not name or name.startswith("-") or any(c.isspace() for c in name):
            return self._record(ToolOutcome(INSTALL_PACKAGE, "failed", False, "package is not a bare name", data=data))
        # `python -m pip`: the ungoverned spelling on purpose. It imports pip
        # in-process and never goes near a PATH shim, so it reaches pip even
        # on an image where a guard IS installed.
        try:
            completed = await asyncio.to_thread(
                subprocess.run,  # noqa: S603 - fixed argv, validated operand
                [sys.executable, "-m", "pip", "install", "--user", name],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return self._record(ToolOutcome(INSTALL_PACKAGE, "failed", False, f"pip install {name} did not finish in 300s", data=data))
        data["exit_code"] = completed.returncode
        if completed.returncode == 0:
            return self._record(
                ToolOutcome(INSTALL_PACKAGE, "pkg_allow", True, f"{name} installed; nothing checked it first.", data=data)
            )
        tail = f"{completed.stdout}\n{completed.stderr}".strip()[-600:]
        return self._record(ToolOutcome(INSTALL_PACKAGE, "failed", False, tail or f"pip exited {completed.returncode}", data=data))
