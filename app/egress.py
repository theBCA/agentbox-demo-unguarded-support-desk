"""Outbound HTTP, the way an application does it when nothing is in the way.

This is where the twin and the starter genuinely differ for going online.
`posture.py` and `tls_trust.py` are byte-identical copies of the starter's,
so the banner and the trust report are the same code reaching a different
answer; this module is the answer's cause.

The starter asks SecureProxy's forward proxy first and refuses a request it
cannot verify. This version does what the request asks: no proxy, no list,
`verify=False` because that is what gets written when TLS gets in the way of
a deadline -- and it is invisible, the call succeeds and the log line looks
identical.
"""

from __future__ import annotations

import os
from typing import Any

PROXY_ENV_VARS: tuple[str, ...] = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
DEFAULT_TIMEOUT_SECONDS = 15.0


def proxy_configuration() -> dict[str, bool]:
    """Which proxy variables are set. Identical to the starter's, and on this
    side it reports the empty answer -- there is no proxy to describe."""
    return {name: bool(os.environ.get(name, "").strip()) for name in PROXY_ENV_VARS}


async def post(url: str, text: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """POST *text* to *url*. Straight out, unverified, unrecorded."""
    import httpx

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        verify=False,  # noqa: S501 - the point of this app
        trust_env=False,
    ) as client:
        response = await client.post(
            url, content=text.encode("utf-8"), headers={"content-type": "text/plain; charset=utf-8"}
        )
    return {"url": url, "status": response.status_code, "body_prefix": response.text[:200]}
