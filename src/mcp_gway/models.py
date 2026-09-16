"""Pydantic models for MCP server configurations (OpenCode-only)."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import re
import socket
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path as _Path
from pathlib import PurePosixPath as _PurePosix
from typing import Any, Literal
from urllib.parse import unquote as _unquote
from urllib.parse import urljoin as _urljoin
from urllib.parse import urlparse as _urlparse_for_validation

import httpx2
from pydantic import BaseModel, ConfigDict, Field, field_validator

SSRF_TIMEOUT = 8.0
SSRF_DNS_TIMEOUT = 3.0
SSRF_MAX_BODY = 1_048_576
SSRF_MAX_REDIRECTS = 3
SSRF_CACHE_TTL = 60.0
SSRF_IDLE_TIMEOUT = 300.0

# Deprecated aliases: SSRF_* is the single source of truth. New code must
# use SSRF_* directly; these remain only for backward compatibility.
_SSRF_CACHE_TTL = SSRF_CACHE_TTL
_SSRF_MAX_BODY = SSRF_MAX_BODY
_SSRF_TIMEOUT = SSRF_TIMEOUT
_SSRF_DNS_TIMEOUT = SSRF_DNS_TIMEOUT
_SSRF_MAX_REDIRECTS = SSRF_MAX_REDIRECTS
_SSRF_DNS_CACHE: dict[str, tuple[float, list[str]]] = {}

_PIN_THREAD_LOCK: Any = __import__("threading").Lock()
_PIN_ASYNC_LOCK: asyncio.Lock | None = None


def _get_pin_lock() -> asyncio.Lock:
    """Return the process-global pin lock (single instance, all loops/threads).

    WHY global: socket.getaddrinfo is process-global, so per-loop locks race
    across threads/loops and leak pins. One global lock serializes pin+connect
    per hop; _pinned_dns acquires the thread lock via to_thread so the event
    loop never blocks. Kept as a function for backward compatibility.
    """
    global _PIN_ASYNC_LOCK
    if _PIN_ASYNC_LOCK is None:
        _PIN_ASYNC_LOCK = asyncio.Lock()
    return _PIN_ASYNC_LOCK


def _require_https(url: str) -> None:
    """Fail-closed https-only gate with [reason=https_only] token."""
    if _urlparse_for_validation(url).scheme != "https":
        raise ValueError("ssrf: https-only [reason=https_only]")


_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
}


_ARG_RE = re.compile(r"^[A-Za-z0-9_./:@-]{1,80}$")


def _validate_name_value(v: str) -> str:
    if not v:
        raise ValueError("Name must not be empty")
    if "/" in v or "\\" in v or v in (".", ".."):
        raise ValueError("Name must not contain path separators or be '.' or '..'")
    if not v.isascii():
        raise ValueError("Name must contain only ASCII characters")
    if "-" in v or " " in v:
        raise ValueError("Name cannot contain hyphens or spaces")
    if v[0].isdigit():
        raise ValueError("Name cannot start with a number")
    if "<" in v or ">" in v or '"' in v or "'" in v or "&" in v:
        raise ValueError("Name contains invalid characters")
    if not _NAME_RE.match(v):
        raise ValueError("Name must match ^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    if v.lower() in _RESERVED_NAMES:
        raise ValueError("Name is reserved")
    return v


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast:
        return True
    if ip.is_reserved or ip.is_unspecified:
        return True
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        if _is_blocked_ip(mapped):
            return True
    return False


def _parse_int_part(text: str) -> int | None:
    t = text.strip()
    if not t:
        return None
    try:
        if t.lower().startswith("0x") and len(t) > 2:
            return int(t, 16)
        if len(t) > 1 and t.startswith("0") and t.isdigit():
            if all(c in "01234567" for c in t):
                return int(t, 8)
            return None
        if t.isdigit():
            return int(t, 10)
        return None
    except ValueError:
        return None


def _legacy_ipv4_to_canonical(host: str) -> str | None:
    if ":" in host:
        return None
    h = host.strip().rstrip(".")
    if not h:
        return None
    if "/" in h or " " in h:
        return None
    parts = h.split(".")
    if len(parts) < 1 or len(parts) > 4:
        return None
    nums: list[int] = []
    for p in parts:
        n = _parse_int_part(p)
        if n is None:
            return None
        nums.append(n)
    if len(nums) == 1:
        n = nums[0]
        if n < 0 or n > 0xFFFFFFFF:
            return None
        return f"{(n >> 24) & 0xFF}.{(n >> 16) & 0xFF}.{(n >> 8) & 0xFF}.{n & 0xFF}"
    if len(nums) == 2:
        a, b = nums
        if a < 0 or a > 255 or b < 0 or b > 0xFFFFFF:
            return None
        return f"{a}.{(b >> 16) & 0xFF}.{(b >> 8) & 0xFF}.{b & 0xFF}"
    if len(nums) == 3:
        a, b, c = nums
        if a < 0 or a > 255 or b < 0 or b > 255 or c < 0 or c > 0xFFFF:
            return None
        return f"{a}.{b}.{(c >> 8) & 0xFF}.{c & 0xFF}"
    a, b, c, d = nums
    for x in (a, b, c, d):
        if x < 0 or x > 255:
            return None
    return f"{a}.{b}.{c}.{d}"


def _raw_netloc(url: str) -> str:
    after = url.split("://", 1)[1] if "://" in url else url
    for sep in ("/", "?", "#"):
        after = after.split(sep, 1)[0]
    return after


def _reject_obscured_netloc(url: str) -> None:
    raw = _raw_netloc(url)
    if "@" in raw:
        raise ValueError("url must not contain userinfo [reason=userinfo]")
    if "%" in raw:
        raise ValueError("url host contains encoded chars [reason=encoded_host]")
    if "\\" in raw or " " in raw:
        raise ValueError("url host contains invalid chars [reason=invalid_host]")
    parsed = _urlparse_for_validation(url)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("url must not contain userinfo [reason=userinfo]")


def _normalize_host(raw_host: str) -> str:
    """Normalize a URL host fail-closed (lowercase, strip trailing dot, IDNA).

    Rejects percent-encoded, userinfo (@), path separators, spaces and
    backslashes before IDNA conversion. Empty results and IDNA errors raise
    ValueError with a [reason=...] token. Callers must treat any raise as
    block (fail-closed); never fall back to the raw host.
    """
    if not raw_host:
        raise ValueError("url must have host [reason=invalid_host]")
    if "%" in raw_host:
        raise ValueError("url host contains encoded chars [reason=encoded_host]")
    decoded = _unquote(raw_host)
    if decoded != raw_host:
        raise ValueError("url host contains encoded chars [reason=encoded_host]")
    if "@" in decoded or "/" in decoded or "\\" in decoded or " " in decoded:
        raise ValueError("url host contains invalid chars [reason=invalid_host]")
    if "%" in decoded:
        raise ValueError("url host contains encoded chars [reason=encoded_host]")
    host = decoded.lower().rstrip(".")
    if not host:
        raise ValueError("url must have host [reason=invalid_host]")
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError) as e:
        raise ValueError(f"url host invalid idna [reason=invalid_host]: {e}") from e
    return host


def _validate_url_structure(url: str) -> tuple[Any, str]:
    if not isinstance(url, str) or not url:
        raise ValueError("url must be non-empty string")
    if "\r" in url or "\n" in url:
        raise ValueError("url must not contain CR or LF")
    _reject_obscured_netloc(url)
    parsed = _urlparse_for_validation(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must be http or https")
    if not parsed.netloc:
        raise ValueError("url must have host")
    raw_host = parsed.hostname or ""
    host = _normalize_host(raw_host)
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("url host not allowed (private/local) [reason=private_ip]")
    return parsed, host


def _is_public_literal_ip(host: str) -> bool:
    """Return True when host is a public IP literal (allowed without DNS).

    Raises ValueError for blocked literals (loopback/private/link-local/
    multicast/reserved/unspecified, incl. legacy octal/hex/int forms and
    IPv4-mapped IPv6). Returns False when host is not an IP literal so the
    caller must resolve DNS next. Never returns True for blocked input.
    """
    canonical = _legacy_ipv4_to_canonical(host)
    candidate = canonical if canonical is not None else host
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    if _is_blocked_ip(ip):
        raise ValueError("url host not allowed (private IP)")
    return True


def _ensure_resolved_ips(ips: list[str]) -> None:
    """Fail-closed DNS gate: empty or zero-parsable blocks; any blocked IP blocks."""
    if not ips:
        raise ValueError("url host DNS failure: no addresses [reason=dns_error]")
    parsable = 0
    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            # WHY narrow: unparsable sockaddr strings are skipped but counted
            # via parsable==0 below, so garbage can never pass as clean.
            continue
        parsable += 1
        if _is_blocked_ip(ip):
            raise ValueError("url host not allowed (private IP)")
    if parsable == 0:
        raise ValueError("url host DNS failure: no addresses [reason=dns_error]")


# Deprecated aliases (backward compatibility with tests/review tooling).
_check_resolved_ips = _ensure_resolved_ips
_check_literal_ip = _is_public_literal_ip
_ensure_literal_ip = _is_public_literal_ip


def _resolve_host_ips(host: str, *, use_cache: bool) -> list[str]:
    key = host.lower().rstrip(".")
    now = time.monotonic()
    if use_cache:
        cached = _SSRF_DNS_CACHE.get(key)
        if cached is not None:
            ts, ips = cached
            if now - ts < SSRF_CACHE_TTL:
                return ips
    try:
        infos = socket.getaddrinfo(
            key, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
    except (socket.gaierror, OSError, UnicodeError) as e:
        raise ValueError(f"url host DNS failure [reason=dns_error]: {e}") from e
    ips: list[str] = []
    for _fam, _typ, _proto, _canon, sockaddr in infos:
        try:
            ip_str = sockaddr[0]
        except (IndexError, TypeError):
            continue
        if ip_str and ip_str not in ips:
            ips.append(ip_str)
    if use_cache and ips:
        _SSRF_DNS_CACHE[key] = (now, ips)
    return ips


async def _aresolve_host_ips(host: str, *, use_cache: bool = False) -> list[str]:
    """Resolve DNS off the event loop with a bounded 3s timeout (fail-closed)."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_resolve_host_ips, host, use_cache=use_cache),
            timeout=SSRF_DNS_TIMEOUT,
        )
    except TimeoutError as e:
        # WHY narrow to timeouts: DNS blocks and slow resolvers must not hang
        # the loop; any timeout is fail-closed as dns_error. Resolver ValueErrors
        # propagate unchanged (already carry [reason=dns_error]).
        raise ValueError("url host DNS timeout [reason=dns_error]") from e


async def _avalidate_url_ssrf(url: str) -> str:
    """Async SSRF gate: structure + literal-IP check, then bounded DNS resolve."""
    _parsed, host = _validate_url_structure(url)
    if _is_public_literal_ip(host):
        return url
    ips = await _aresolve_host_ips(host, use_cache=False)
    _ensure_resolved_ips(ips)
    return url


avalidate_url_ssrf = _avalidate_url_ssrf


def validate_url_ssrf(url: str, *, use_cache: bool = True) -> str:
    _parsed, host = _validate_url_structure(url)
    if _is_public_literal_ip(host):
        return url
    ips = _resolve_host_ips(host, use_cache=use_cache)
    _ensure_resolved_ips(ips)
    return url


@contextlib.contextmanager
def _pin_host_to_ips(host: str, ips: list[str]):  # type: ignore[no-untyped-def]
    """Pin hostname to resolve-once IPs; URL keeps hostname so Host/SNI preserved.

    Process-global patch: callers MUST serialize via _pinned_dns (async lock).
    Direct use in overlapping async fetches races; _send_pinned never uses this
    directly anymore.
    """
    key = host.lower().rstrip(".")
    original = socket.getaddrinfo

    def _fake(h: str, port: int | None, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        if isinstance(h, str) and h.lower().rstrip(".") == key:
            pinned: list[Any] = []
            for ip in ips:
                try:
                    parsed_ip = ipaddress.ip_address(ip)
                except ValueError:
                    # WHY narrow: skip garbage pins; empty pin below raises
                    # gaierror fail-closed instead of falling back to real DNS.
                    continue
                if isinstance(parsed_ip, ipaddress.IPv6Address):
                    pinned.append(
                        (
                            socket.AF_INET6,
                            socket.SOCK_STREAM,
                            6,
                            "",
                            (ip, port or 0, 0, 0),
                        )
                    )
                else:
                    pinned.append(
                        (
                            socket.AF_INET,
                            socket.SOCK_STREAM,
                            6,
                            "",
                            (ip, port or 0),
                        )
                    )
            if pinned:
                return pinned
            raise socket.gaierror("pinned DNS: no addresses")
        return original(h, port, *args, **kwargs)

    socket.getaddrinfo = _fake  # type: ignore[method-assign]
    try:
        yield ips
    finally:
        socket.getaddrinfo = original  # type: ignore[method-assign]


@contextlib.asynccontextmanager
async def _pinned_dns(host: str, ips: list[str]) -> AsyncIterator[list[str]]:
    """Concurrency-safe pin: process-global getaddrinfo patch under a global lock.

    WHY global: socket.getaddrinfo is process-global, so two overlapping
    fetches for different hosts would overwrite each other's pin. The global
    threading lock is acquired via to_thread (never blocking the event loop)
    so overlapping pins from any loop/thread serialize per hop, giving
    per-hop isolation (see tests/test_ssrf_pin_isolation.py). Hosts are
    matched case-insensitively on the normalized (punycode) form.
    """
    normalized = host.lower().rstrip(".")
    await asyncio.to_thread(_PIN_THREAD_LOCK.acquire)
    try:
        with _pin_host_to_ips(normalized, ips):
            yield ips
    finally:
        try:
            _PIN_THREAD_LOCK.release()
        except Exception:
            pass


async def _resolve_ips_for_pin(host: str) -> list[str]:
    """Resolve-once helper for pinned fetches; pin via _pinned_dns only."""
    ips = await _aresolve_host_ips(host, use_cache=False)
    _ensure_resolved_ips(ips)
    return ips


def _is_redirect_status(status: int) -> bool:
    return status in (301, 302, 303, 307, 308)


def _ensure_body_limits(resp: Any) -> None:
    """Enforce 1MB response cap via content-length pre-check plus body length.

    Buffered fallback only. Streaming callers must use _enforce_streaming_cap
    so chunked bodies without content-length are capped incrementally and
    never fully buffered (100MB chunked must fail at ~1MB, not after OOM).
    """
    headers = getattr(resp, "headers", {}) or {}
    clen = headers.get("content-length", headers.get("Content-Length"))
    try:
        clen_int = int(clen) if clen is not None else None
    except (ValueError, TypeError):
        # WHY narrow: malformed content-length must not bypass the cap; fall
        # through to the body-length check below instead of raising here.
        clen_int = None
    if clen_int is not None and clen_int > SSRF_MAX_BODY:
        raise ValueError("ssrf: response too large [reason=response_too_large]")
    content = getattr(resp, "content", b"")
    try:
        if content is not None and len(content) > SSRF_MAX_BODY:
            raise ValueError("ssrf: response too large [reason=response_too_large]")
    except TypeError:
        # WHY narrow: non-sized bodies (streams/None) have nothing to cap here;
        # streaming callers enforce the cap incrementally.
        pass


async def _enforce_streaming_cap(resp: Any) -> None:
    """Incremental 1MB cap for streaming/chunked bodies (no full buffering)."""
    headers = getattr(resp, "headers", {}) or {}
    clen = headers.get("content-length", headers.get("Content-Length"))
    try:
        clen_int = int(clen) if clen is not None else None
    except (ValueError, TypeError):
        clen_int = None
    if clen_int is not None and clen_int > SSRF_MAX_BODY:
        raise ValueError("ssrf: response too large [reason=response_too_large]")
    aiter = getattr(resp, "aiter_bytes", None)
    if aiter is None:
        _ensure_body_limits(resp)
        return
    total = 0
    try:
        async for chunk in aiter():
            total += len(chunk)
            if total > SSRF_MAX_BODY:
                raise ValueError("ssrf: response too large [reason=response_too_large]")
    except ValueError:
        raise
    except Exception:
        _ensure_body_limits(resp)


_check_body_limits = _ensure_body_limits


def _resolve_redirect_target(current: str, location: str, hop: int) -> str:
    """Sync redirect gate (structure + https-only + sync DNS); async path uses _aresolve_redirect_target."""
    if not location:
        raise ValueError("ssrf: empty redirect [reason=redirect]")
    if hop >= SSRF_MAX_REDIRECTS:
        raise ValueError("ssrf: too many redirects [reason=redirect]")
    nxt = _urljoin(current, location)
    pn = _urlparse_for_validation(nxt)
    if pn.scheme != "https":
        raise ValueError("ssrf: https-only redirect [reason=redirect]")
    validate_url_ssrf(nxt, use_cache=False)
    return nxt


async def _aresolve_redirect_target(current: str, location: str, hop: int) -> str:
    """Async redirect gate: same checks as sync but DNS via bounded to_thread.

    Validates structure + https-only, then atomically resolves-and-gates the
    next hop with _avalidate_url_ssrf (fail-closed). Called once per hop from
    _ssrf_fetch so no sync getaddrinfo ever blocks the event loop.
    """
    if not location:
        raise ValueError("ssrf: empty redirect [reason=redirect]")
    if hop >= SSRF_MAX_REDIRECTS:
        raise ValueError("ssrf: too many redirects [reason=redirect]")
    nxt = _urljoin(current, location)
    pn = _urlparse_for_validation(nxt)
    if pn.scheme != "https":
        raise ValueError("ssrf: https-only redirect [reason=redirect]")
    await _avalidate_url_ssrf(nxt)
    return nxt


async def _send_pinned(
    client: Any,
    method: str,
    url: str,
    host: str,
    *,
    headers: dict[str, str] | None,
    json_body: dict[str, object] | None,
    data: dict[str, str] | None,
) -> Any:
    """Resolve-once per hop; pinned connect under the global pin lock (isolation).

    Prefers client.stream (incremental 1MB cap, no OOM on chunked) when the
    client supports it; falls back to buffered get/post for test doubles.
    Host must already be normalized (punycode, lowercase) by the caller.
    """
    normalized = host.lower().rstrip(".")
    if _is_public_literal_ip(normalized):
        return await _fetch_via_client(
            client, method, url, headers=headers, json_body=json_body, data=data
        )
    ips = await _aresolve_host_ips(normalized, use_cache=False)
    _ensure_resolved_ips(ips)
    async with _pinned_dns(normalized, ips):
        return await _fetch_via_client(
            client, method, url, headers=headers, json_body=json_body, data=data
        )


async def _fetch_via_client(
    client: Any,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None,
    json_body: dict[str, object] | None,
    data: dict[str, str] | None,
) -> Any:
    """Fetch via streaming when available (incremental cap), else buffered."""
    stream = getattr(client, "stream", None)
    if stream is not None:
        try:
            if method == "GET":
                async with stream(
                    "GET", url, headers=headers, follow_redirects=False
                ) as resp:
                    await _enforce_streaming_cap(resp)
                    return resp
            async with stream(
                "POST",
                url,
                headers=headers,
                json=json_body,
                data=data,
                follow_redirects=False,
            ) as resp:
                await _enforce_streaming_cap(resp)
                return resp
        except ValueError:
            raise
        except AttributeError:
            pass
        except TypeError:
            pass
    if method == "GET":
        resp = await client.get(url, headers=headers, follow_redirects=False)
    else:
        resp = await client.post(
            url, headers=headers, json=json_body, data=data, follow_redirects=False
        )
    _ensure_body_limits(resp)
    return resp


def make_ssrf_http_client(
    headers: dict[str, str] | None = None,
) -> Any:
    """Build the single SSRF-port httpx client (8s timeout, no redirects).

    All plain-HTTP remote fetches (OAuth discovery, transport probes) must use
    this: pin comes from _pinned_dns per hop, https-only + max-3 + 1MB are
    enforced by _ssrf_fetch/_ensure_body_limits, follow_redirects=False keeps
    redirect validation manual and atomic per hop.
    """
    return httpx2.AsyncClient(
        timeout=SSRF_TIMEOUT, headers=headers, follow_redirects=False
    )


async def _ssrf_fetch(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, object] | None = None,
    data: dict[str, str] | None = None,
) -> Any:
    parsed0 = _urlparse_for_validation(url)
    if parsed0.scheme != "https":
        raise ValueError("ssrf: https-only [reason=https_only]")
    # resolve-once per hop inside loop (no pre-resolve here to avoid double DNS);
    # _validate_url_structure is pure parsing (no I/O) so it stays sync here.
    # follow_redirects=False is enforced inside make_ssrf_http_client: redirects
    # stay manual so each hop is atomically re-validated and re-pinned.
    _validate_url_structure(url)
    current = url
    async with make_ssrf_http_client() as client:
        for hop in range(SSRF_MAX_REDIRECTS + 1):
            p = _urlparse_for_validation(current)
            if p.scheme != "https":
                raise ValueError("ssrf: https-only redirect [reason=redirect]")
            _p, host = _validate_url_structure(current)
            resp = await _send_pinned(
                client,
                method,
                current,
                host,
                headers=headers,
                json_body=json_body,
                data=data,
            )
            status = getattr(resp, "status_code", 200)
            if _is_redirect_status(status):
                loc = (
                    resp.headers.get("location", "") if hasattr(resp, "headers") else ""
                )
                if not loc:
                    return resp
                current = await _aresolve_redirect_target(current, loc, hop)
                continue
            return resp
    raise ValueError("ssrf: too many redirects [reason=redirect]")


async def ssrf_get(url: str, *, headers: dict[str, str] | None = None) -> Any:
    return await _ssrf_fetch("GET", url, headers=headers)


async def ssrf_post(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, object] | None = None,
    data: dict[str, str] | None = None,
) -> Any:
    return await _ssrf_fetch("POST", url, headers=headers, json_body=json, data=data)


class ToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class OAuthConfig(BaseModel):
    clientId: str | None = None
    clientSecret: str | None = None
    scope: str | None = None

    @field_validator("clientId")
    @classmethod
    def validate_client_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid_obj = uuid.UUID(v)
            return str(uuid_obj)
        except Exception:
            return str(uuid.uuid4())


class MCPServerConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: Literal["local", "remote"]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name_value(v)

    enabled: bool = True
    timeout: int = 5000
    # FEAT-007 (BR-112): opt-in single retry when the TRANSPORT/connect phase
    # fails (never after session.call_tool — non-idempotent side effects).
    # Default off → zero behavior change for existing configs (ADR-012 decision 9).
    retry_on_transport_error: bool = False

    # Bifrost CodeMode alignment: per-client opt-in + allow-list.
    # is_code_mode_client=False hides the server from CodeMode VFS/sandbox.
    # tools_to_execute=["*"] exposes all tools; otherwise exact allow-list.
    is_code_mode_client: bool = True
    tools_to_execute: list[str] = Field(default_factory=lambda: ["*"])
    # Bifrost Agent Mode: tools the agent loop may auto-execute without
    # per-tool approval. [] = all manual; ["*"] = all executable auto-run.
    tools_to_auto_execute: list[str] = Field(default_factory=list)

    # type=local
    command: list[str] | None = None
    cwd: str | None = None
    environment: dict[str, str] | None = None

    # type=remote
    url: str | None = None
    headers: dict[str, str] | None = None
    oauth: OAuthConfig | bool | None = None

    # Internal: resolved after connection test, stored in JSON
    resolved_transport: Literal["sse", "streamable-http", "http"] | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_url_ssrf(v, use_cache=True)

    @field_validator("oauth", mode="before")
    @classmethod
    def validate_oauth(cls, v: Any) -> Any:
        if v is None or v is False:
            return v
        if v is True:
            return {"clientId": str(uuid.uuid4())}
        if isinstance(v, dict):
            if not v.get("clientId"):
                v = dict(v)
                v["clientId"] = str(uuid.uuid4())
            else:
                try:
                    uuid.UUID(str(v["clientId"]))
                except Exception:
                    v = dict(v)
                    v["clientId"] = str(uuid.uuid4())
            return v
        if isinstance(v, OAuthConfig):
            if not v.clientId:
                v.clientId = str(uuid.uuid4())
            else:
                try:
                    uuid.UUID(v.clientId)
                except Exception:
                    v.clientId = str(uuid.uuid4())
            return v
        return v

    @field_validator("command")
    @classmethod
    def validate_cmd(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        from mcp_gway.core.policy import validate_command_syntax

        try:
            validate_command_syntax(v)
        except ValueError as e:
            raise ValueError(str(e)) from None
        return v

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not isinstance(v, str) or not v.strip():
            raise ValueError("cwd must be absolute path [reason=invalid_cwd]")
        text = v.strip()
        is_abs = _Path(text).is_absolute() or _PurePosix(text).is_absolute()
        if not is_abs:
            raise ValueError("cwd must be absolute path [reason=invalid_cwd]")
        return text

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        if v is None:
            return v
        from mcp_gway.core.policy import check_environment

        return check_environment(v)

    def model_post_init(self, __context: Any) -> None:
        if self.type == "local":
            if not self.command:
                raise ValueError("'command' required for type=local")
        elif self.type == "remote":
            if not self.url:
                raise ValueError("'url' required for type=remote")


class MCPServerState(BaseModel):
    name: str
    config: MCPServerConfig
    tools: list[ToolInfo] = Field(default_factory=list)
    state: str = "healthy"
