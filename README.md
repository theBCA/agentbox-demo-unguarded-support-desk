# demos/unguarded-support-desk

> **Deliberately unprotected. Demo only.** This application holds a real provider key in its
> own environment, sends whatever it is told to any address, installs whatever it is asked to and
> checks nothing -- that is what it is for. Run it on a laptop, next to the AgentBox starter, to
> show the difference. Never deploy it, never point it at a real customer system, and never give
> it a key you would mind losing.

**The same job as `starter-apps/support-desk`, with nothing wrapping it.**
Same page, same eight buttons, same customer system beside it -- built on a
different agent SDK (OpenAI) and running on its own. The only difference is
that no platform is in the way, which makes the comparison a measurement
rather than a claim.

Run it next to the real starter and open both windows side by side:

| | |
|---|---|
| `http://127.0.0.1:8080/` | the starter, onboarded into AgentBox |
| `http://127.0.0.1:9099/` | this app, `docker compose up` |

```bash
cp .env.example .env     # paste a real OpenAI key -- see below
docker compose up --build
```

`docker compose` also starts the customer system (the very server the
starter bundles, vendored here as `crm/`, byte-identical to `starter-apps/support-desk/mcp/crm`) and hands
this app its address. The agent calls it directly.

## Three things to be clear about before you show it

**It must run OUTSIDE AgentBox.** Onboard it through the admin console and
AgentBox wraps it like any other application -- gVisor, Package Guard, a
virtual key, an egress policy -- and the red pill turns green. That is worth
doing as the *last* step of a demo; it is not the unguarded side of the
comparison.

**It holds a real provider key**, and that is the first thing being shown.
An unwrapped agentic app has a vendor credential in its environment,
readable by its own code, by every package it imports and by anything an
agent talks it into running. Step 8 asks the agent about it, and the page
reads the answer from `/runtime-info`, not from the model.

**Step 7 names a different package on purpose.** The protected side is asked
for `colourama`, a real typosquat that shipped a clipboard hijacker, and
Package Guard refuses it. This side would actually install what it is asked
for, so its script asks for `colorama` -- the real, harmless package -- and
the page still says truthfully that nobody looked at it. Never run real
malware to make a point.

## What is shared and what is not

Byte-identical with the starter, held by
`tests/unit/tools/test_unguarded_twin_shares_the_console.py`: `ui/` (the
page and its fonts), `app/posture.py` (the banner's derivation),
`app/tls_trust.py`, `concept/prompt.md` (the job). Deliberately different:
`app/main.py` (five routes, no policy normalisation), `app/egress.py` (no
proxy, `verify=False`), `app/agent_tools.py` (an install that reaches pip, a
post that goes straight out), `app/backends/openai_backend.py` (straight to
the vendor with a real key, the customer system reached directly),
`Dockerfile` (no guard stage, writable rootfs).
