"""HTTP plumbing shared by the search backends.

Every backend reports what happened to each ``(source, query)`` pair in a
:class:`SearchStatus` instead of printing an error and returning an empty or
truncated list that looks like a real result. :func:`get` retries 429 and 5xx
answers and network errors a bounded number of times with exponential backoff,
and every wait checks ``should_cancel`` so a stop request is honoured within
about half a second.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional
from urllib.parse import quote, quote_plus

import requests

from .. import __version__

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

USER_AGENT = f"prisma-review-tool/{__version__} (+https://github.com/Black-Lights/prisma-review-tool)"

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 4
BACKOFF_SECONDS = 2.0
# A Retry-After longer than this (e.g. a daily budget that is used up) is not
# worth waiting for inside a pipeline run: the query is reported instead.
MAX_WAIT_SECONDS = 60.0

STATUSES = ("ok", "partial", "failed", "skipped", "cancelled")

# Indirections so tests can stub the network and the clock.
_sleep = time.sleep


def _send(url: str, **kwargs) -> requests.Response:
    return requests.get(url, **kwargs)


class SearchCancelled(Exception):
    """The caller asked to stop while a search was running."""


class SearchRequestError(Exception):
    """A request still failed after the bounded retries."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SearchStatus:
    """Outcome of one ``(source, query)`` search.

    ``status`` is ``ok``, ``partial`` (some records came back, then the search
    stopped early), ``failed`` (nothing usable came back), ``skipped`` (not
    run) or ``cancelled``. ``api_total`` is the number of matches the API
    reported (None when it does not say), ``retrieved`` the records parsed.
    ``executed`` is the query string exactly as sent and ``request`` the
    endpoint and parameters (never API keys or the contact email).
    """

    source: str = ""
    status: str = "ok"
    error: Optional[str] = None
    api_total: Optional[int] = None
    retrieved: int = 0
    executed: Optional[str] = None
    request: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Post-request filters that must not run on this result (e.g. require_abstract
    # when Scopus fell back to a view without abstracts).
    skip_post_filters: set[str] = field(default_factory=set)

    def stop(self, message: str, have_results: bool) -> None:
        """Record why the search stopped early: partial if records came back, else failed."""
        self.status = "partial" if have_results else "failed"
        self.error = message

    def cancel(self) -> None:
        self.status = "cancelled"
        self.error = "cancelled by the user"


# "url: /works?query=x&mailto=a%40b.org" in a requests exception message.
_URL_QUERY_RE = re.compile(r"(url: [^\s?]*)\?[^\s)]*")


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every non-empty secret in ``text`` with ``***``.

    Also its URL-encoded forms: requests quotes the query string it sent
    (``mailto=someone%40example.org``) in its exception messages.
    """
    for secret in secrets:
        if not secret:
            continue
        for form in {secret, quote(secret, safe=""), quote(secret), quote_plus(secret)}:
            text = text.replace(form, "***")
    return text


def strip_query(text: str) -> str:
    """Drop the query string of any ``url: ...`` in an exception message.

    The request itself is recorded in the search log (without credentials), so
    the parameters add nothing to an error and may carry a contact email.
    """
    return _URL_QUERY_RE.sub(r"\1?...", text)


def error_text(exc: BaseException, secrets: Iterable[str] = ()) -> str:
    """``"<Type>: <message>"`` for an exception, query strings and secrets removed."""
    return redact(strip_query(f"{type(exc).__name__}: {exc}"), secrets)


def check_cancel(should_cancel: Optional[Callable[[], bool]]) -> None:
    if should_cancel is not None and should_cancel():
        raise SearchCancelled()


def wait(seconds: float, should_cancel: Optional[Callable[[], bool]] = None) -> None:
    """Sleep in short steps so a cancel request interrupts the wait."""
    remaining = max(0.0, float(seconds))
    while True:
        check_cancel(should_cancel)
        if remaining <= 0:
            return
        step = min(0.5, remaining)
        _sleep(step)
        remaining -= step


def _retry_after(resp: requests.Response) -> Optional[float]:
    value = (getattr(resp, "headers", None) or {}).get("Retry-After")
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None  # an HTTP date: fall back to our own backoff


def api_error_code(resp: requests.Response, limit: int = 120) -> str:
    """Only the short ``error`` field of a JSON error body (no free-text ``message``)."""
    try:
        data = resp.json()
    except ValueError:
        return ""
    value = data.get("error") if isinstance(data, dict) else None
    return " ".join(str(value).split())[:limit] if isinstance(value, str) else ""


def api_message(resp: requests.Response, limit: int = 300) -> str:
    """A short human-readable error from an API response body."""
    try:
        data = resp.json()
    except ValueError:
        data = None
    parts: list[str] = []
    if isinstance(data, dict):
        for key in ("error", "message", "service-error"):
            value = data.get(key)
            if isinstance(value, dict):
                value = value.get("status", {}).get("statusText") if "status" in value else str(value)
            if value and str(value) not in parts:
                parts.append(str(value).strip().rstrip("."))
    text = ": ".join(parts) if parts else (getattr(resp, "text", "") or "").strip()
    return " ".join(text.split())[:limit]


def get(url: str, *, params: Optional[dict] = None, headers: Optional[dict] = None,
        timeout: float = 30, should_cancel: Optional[Callable[[], bool]] = None,
        max_retries: int = MAX_RETRIES, backoff: float = BACKOFF_SECONDS,
        secrets: Iterable[str] = (), label: str = "") -> requests.Response:
    """GET with bounded retries on 429, 5xx and network errors.

    Returns the response for any other status (the caller decides what a 4xx
    means). Raises :class:`SearchRequestError` once the retries are used up and
    :class:`SearchCancelled` if ``should_cancel`` turns true while waiting.
    ``secrets`` are scrubbed from every error message.
    """
    secrets = [s for s in secrets if s]
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    last_error = ""
    last_code: Optional[int] = None
    for attempt in range(max_retries + 1):
        check_cancel(should_cancel)
        delay = backoff * (2 ** attempt)
        try:
            resp = _send(url, params=params, headers=hdrs, timeout=timeout)
        except requests.RequestException as exc:
            last_error = error_text(exc, secrets)
            last_code = None
        else:
            if resp.status_code not in RETRY_STATUSES:
                return resp
            last_code = resp.status_code
            detail = api_message(resp)
            last_error = redact(f"HTTP {resp.status_code}" + (f" ({detail})" if detail else ""), secrets)
            asked = _retry_after(resp)
            if asked is not None:
                if asked > MAX_WAIT_SECONDS:
                    raise SearchRequestError(
                        f"{last_error}; the API asked to wait {int(asked)} s before retrying",
                        last_code)
                delay = max(delay, asked)
        if attempt == max_retries:
            break
        delay = min(delay, MAX_WAIT_SECONDS)
        print(f"    [!] {label or 'request'}: {last_error}; retrying in {delay:.0f}s "
              f"({attempt + 1}/{max_retries})")
        wait(delay, should_cancel)
    raise SearchRequestError(f"{last_error} (gave up after {max_retries + 1} attempts)", last_code)
