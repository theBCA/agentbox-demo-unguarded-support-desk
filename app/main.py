"""Support Desk, unguarded -- the same job with nothing wrapping it.

This is the twin of `starter-apps/support-desk`, and it exists so the
comparison is measured rather than described. It serves the SAME page
(`ui/index.html` is a byte-identical copy, held there by a test) and the same
script (`concept/`), so a prospect can put the two side by side and the only
difference is what the platform is doing.

**It must run OUTSIDE AgentBox.** Upload it through the admin console and
AgentBox wraps it like anything else -- gVisor, Package Guard, a virtual key,
an egress policy -- and the demo inverts: the red banner turns green and this
file's whole point disappears. `docker compose up` on :9099 is how it runs.

**It holds a real provider key**, `OPENAI_API_KEY` in `.env`. That is not a
shortcut, it is the first thing being demonstrated.

Nothing here pretends. There is no demo mode and no faked refusal: the app
reports what happened, and what happened is that nothing stopped it.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_CONCEPT_FILE = Path(__file__).resolve().parent.parent / "concept" / "concept.json"


def _concept_name() -> str:
    try:
        return str(json.loads(_CONCEPT_FILE.read_text(encoding="utf-8")).get("name") or "")
    except (OSError, ValueError):
        return ""


app = FastAPI(title=f"{_concept_name() or 'Agent'} (unguarded)")


class ProcessRequest(BaseModel):
    input: str | None = None
    document: str | None = None
    question: str | None = None

    def text(self) -> str:
        source = self.input if self.input is not None else self.document
        return (source or "").strip()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/runtime-info")
async def runtime_info() -> dict:
    """The same posture probe the starter serves, from the same module.

    Byte-identical to `starter-apps/support-desk/app/posture.py`, which is
    what makes the two banners comparable: one implementation, reaching
    opposite answers because the environments genuinely differ. If this
    returned a hand-written red banner it would prove nothing.
    """
    from app import posture

    return posture.describe()


@app.get("/concept")
async def concept() -> dict:
    """The same script the starter's page reads, so the two windows show the
    same eight buttons. Only the sentences the page picks differ, and it
    picks them from `/runtime-info`, not from this file. (One prompt differs:
    the install step names a real, harmless package here -- the typosquat
    the protected side is asked for is real malware, and this side would
    actually install it.)"""
    try:
        return json.loads(_CONCEPT_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="no concept/concept.json") from exc


@app.post("/process")
async def process_message(payload: ProcessRequest) -> dict:
    text = payload.text()
    if not text:
        raise HTTPException(status_code=400, detail="input must not be empty")
    from app.backends import openai_backend

    result = await openai_backend.process(text, payload.question)
    result["backend"] = "openai (direct to vendor)"
    return result


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/process/stream")
async def process_message_streaming(payload: ProcessRequest) -> StreamingResponse:
    text = payload.text()
    if not text:
        raise HTTPException(status_code=400, detail="input must not be empty")
    from app.backends import openai_backend

    async def events():
        yield _sse("start", {"backend": "openai (direct to vendor)"})
        try:
            async for event in openai_backend.stream(text, payload.question):
                kind = str(event.get("type") or "token")
                yield _sse(kind, {k: v for k, v in event.items() if k != "type"})
        except Exception as exc:  # noqa: BLE001 - surfaced as a stream event
            # No normalisation of policy blocks, because there is no policy to
            # block anything. Whatever went wrong here is an ordinary bug or a
            # missing key, and saying so is the honest answer.
            yield _sse("error", {"detail": str(exc), "status": 500})
        yield _sse("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True, check_dir=False), name="ui")
