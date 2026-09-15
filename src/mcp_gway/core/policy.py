"""Local command policy — allow-list + unrestricted TTL + cwd/env gates."""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOW_LIST_ENV = "MCP_GWAY_ALLOW_LOCAL_COMMANDS"
UNRESTRICTED_ENV = "MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL"

# Default allow-list when MCP_GWAY_ALLOW_LOCAL_COMMANDS is unset or empty.
# Replaces the old default-deny: npx/bunx/uvx/pipx runner shims are allowed
# out of the box; set the env var to override, break-glass still bypasses.
DEFAULT_ALLOW_LIST = frozenset({"npx", "bunx", "uvx", "pipx"})

MARKER_NAME = ".local_unrestricted"
UNRESTRICTED_TTL_SECONDS = 72 * 3600

ENV_DENYLIST_EXACT = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "COMSPEC",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NODE_EXTRA_CA_CERTS",
        "NODE_TLS_REJECT_UNAUTHORIZED",
    }
)
ENV_DENYLIST_PREFIXES = ("DYLD_", "NPM_CONFIG_", "BUN_", "UV_")

_ARG_RE = re.compile(r"^[A-Za-z0-9_./:@-]{1,80}$")
_BASENAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$")


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str
    message: str


@dataclass(frozen=True)
class UnrestrictedStatus:
    active: bool
    state: str
    marker_exists: bool
    age_seconds: float | None
    expires_in_seconds: float | None


def config_dir() -> Path:
    return Path.home() / ".config" / "mcp-gway"


def marker_path() -> Path:
    return config_dir() / MARKER_NAME


def get_allow_list() -> set[str]:
    """Parse allow-list CSV; matching is case-insensitive (lowercased, deduped).

    When MCP_GWAY_ALLOW_LOCAL_COMMANDS is unset or blank, returns the
    DEFAULT_ALLOW_LIST (npx, bunx, uvx, pipx). An explicit non-blank value
    overrides the default. ``*``/paths/invalid entries are denied with warn.
    Callers compare ``basename.lower()`` against this set; PATH
    resolution itself stays platform-native.
    """
    raw = os.environ.get(ALLOW_LIST_ENV, "")
    if not raw.strip():
        return set(DEFAULT_ALLOW_LIST)
    parts = [p.strip() for p in raw.split(",")]
    result: set[str] = set()
    for p in parts:
        if not p:
            continue
        if p == "*" or "*" in p:
            logger.warning("allow-list wildcard denied: %s", ALLOW_LIST_ENV)
            continue
        if "/" in p or "\\" in p or p in (".", "..") or ".." in p:
            logger.warning("allow-list entry invalid, denied: %s", p[:32])
            continue
        if not _BASENAME_RE.match(p):
            logger.warning("allow-list entry invalid, denied: %s", p[:32])
            continue
        result.add(p.lower())
    return result


def create_unrestricted_marker(now: float | None = None) -> Path:
    """Create break-glass marker with epoch content, atomic write, 0o600 on posix."""
    epoch = int(now if now is not None else time.time())
    path = marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".local_unrestricted-")
    try:
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        with f:
            f.write(str(epoch))
        # Double-chmod: mkstemp mode is umask-dependent on replace targets,
        # so enforce 0o600 on tmp before replace and on final path after.
        if os.name != "nt":
            os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    logger.info("unrestricted marker created path=%s", str(path))
    return path


def remove_unrestricted_marker() -> bool:
    """Remove break-glass marker.

    Returns True when a file was removed, False when missing.
    Raises OSError when removal fails so CLI can distinguish missing vs failure.
    """
    path = marker_path()
    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError as e:
        logger.warning(
            "unrestricted marker remove failed, denied: %s", type(e).__name__
        )
        raise
    logger.info("unrestricted marker removed path=%s", str(path))
    return True


def unrestricted_status(now: float | None = None) -> UnrestrictedStatus:
    """Inspect break-glass state without side effects."""
    current = time.time() if now is None else now
    if os.environ.get(UNRESTRICTED_ENV) != "1":
        return UnrestrictedStatus(
            active=False,
            state="disabled",
            marker_exists=marker_path().exists(),
            age_seconds=None,
            expires_in_seconds=None,
        )
    marker = marker_path()
    if not marker.exists():
        return UnrestrictedStatus(
            active=False,
            state="marker-missing",
            marker_exists=False,
            age_seconds=None,
            expires_in_seconds=None,
        )
    try:
        st = marker.stat()
        if os.name != "nt":
            mode = stat.S_IMODE(st.st_mode)
            if mode != 0o600:
                logger.warning(
                    "unrestricted marker insecure permissions %o, denied",
                    mode,
                )
                return UnrestrictedStatus(
                    active=False,
                    state="marker-insecure",
                    marker_exists=True,
                    age_seconds=None,
                    expires_in_seconds=None,
                )
    except OSError as e:
        logger.warning("unrestricted marker stat failed, denied: %s", type(e).__name__)
        return UnrestrictedStatus(
            active=False,
            state="marker-unreadable",
            marker_exists=True,
            age_seconds=None,
            expires_in_seconds=None,
        )
    try:
        with marker.open("r", encoding="utf-8") as f:
            text = f.read(64).strip()
    except Exception as e:
        logger.warning("unrestricted marker unreadable, denied: %s", type(e).__name__)
        return UnrestrictedStatus(
            active=False,
            state="marker-unreadable",
            marker_exists=True,
            age_seconds=None,
            expires_in_seconds=None,
        )
    if not text:
        return UnrestrictedStatus(
            active=False,
            state="marker-invalid",
            marker_exists=True,
            age_seconds=None,
            expires_in_seconds=None,
        )
    try:
        epoch = int(text.split()[0])
    except (ValueError, IndexError):
        return UnrestrictedStatus(
            active=False,
            state="marker-invalid",
            marker_exists=True,
            age_seconds=None,
            expires_in_seconds=None,
        )
    age = current - epoch
    if age < 0:
        return UnrestrictedStatus(
            active=False,
            state="future",
            marker_exists=True,
            age_seconds=age,
            expires_in_seconds=None,
        )
    if age > UNRESTRICTED_TTL_SECONDS:
        return UnrestrictedStatus(
            active=False,
            state="expired",
            marker_exists=True,
            age_seconds=age,
            expires_in_seconds=None,
        )
    return UnrestrictedStatus(
        active=True,
        state="active",
        marker_exists=True,
        age_seconds=age,
        expires_in_seconds=UNRESTRICTED_TTL_SECONDS - age,
    )


def is_unrestricted_active(now: float | None = None) -> bool:
    return unrestricted_status(now=now).active


def validate_command_syntax(command: list[str]) -> str:  # noqa: TRY004
    if not isinstance(command, list):
        raise ValueError("command must be list [reason=invalid_syntax]")  # noqa: TRY004
    if len(command) == 0 or len(command) > 8:
        raise ValueError("command must have 1-8 tokens [reason=invalid_syntax]")
    basename = command[0]
    if not isinstance(basename, str):
        raise ValueError("command token must be string [reason=invalid_syntax]")  # noqa: TRY004
    if "/" in basename or "\\" in basename or ":" in basename:
        raise ValueError(
            f"command must be basename, not path: {basename} [reason=invalid_syntax]"
        )
    if not _BASENAME_RE.match(basename):
        raise ValueError(f"command token invalid: {basename} [reason=invalid_syntax]")
    for tok in command:
        if not isinstance(tok, str):
            raise ValueError("command token must be string [reason=invalid_syntax]")  # noqa: TRY004
        if len(tok) == 0 or len(tok) > 80:
            raise ValueError("command token length 1-80 [reason=invalid_syntax]")
        if not _ARG_RE.match(tok):
            raise ValueError(f"command token invalid: {tok} [reason=invalid_syntax]")
        if ".." in tok:
            raise ValueError(
                "command token must not contain .. [reason=invalid_syntax]"
            )
        if tok == "/":
            raise ValueError("command token must not be / [reason=invalid_syntax]")
        if any(c in tok for c in (";", "&", "$", "(", ")", "|", "`")):
            raise ValueError(
                "command token contains forbidden chars [reason=invalid_syntax]"
            )
    return basename


def resolve_binary(basename: str) -> str | None:
    try:
        return shutil.which(basename)
    except Exception:
        return None


def _not_allowlisted_message(basename: str, detail: str) -> str:
    return f"command not allowed: {basename} ({detail}) [reason=not_allowlisted]"


def _break_glass_detail(status: UnrestrictedStatus) -> str:
    """Human-readable break-glass hint for deny messages (no raw enum leak)."""
    if status.state == "marker-missing":
        return (
            "break-glass marker missing; run `mcp-gway local-unrestricted enable` "
            f"with {UNRESTRICTED_ENV}=1"
        )
    if status.state == "expired":
        return "break-glass marker expired; re-run `mcp-gway local-unrestricted enable`"
    if status.state == "future":
        return (
            "break-glass marker timestamp in the future; re-run "
            "`mcp-gway local-unrestricted enable`"
        )
    if status.state == "marker-insecure":
        return (
            "break-glass marker has insecure permissions; re-run "
            "`mcp-gway local-unrestricted enable`"
        )
    if status.state == "marker-unreadable":
        return (
            "break-glass marker unreadable; re-run `mcp-gway local-unrestricted enable`"
        )
    if status.state == "marker-invalid":
        return "break-glass marker invalid; re-run `mcp-gway local-unrestricted enable`"
    return "break-glass inactive; run `mcp-gway local-unrestricted status`"


def check_basename_allowed(basename: str, *, host_loopback: bool) -> PolicyDecision:
    _ = host_loopback  # reserved for future host-gating; basename policy is host-independent
    status = unrestricted_status()
    if status.active:
        return PolicyDecision(
            allowed=True, reason_code="unrestricted", message="allowed (unrestricted)"
        )
    allow = get_allow_list()
    if basename.lower() in allow:
        return PolicyDecision(
            allowed=True, reason_code="allow_list", message="allowed (allow-list)"
        )
    if status.state != "disabled":
        detail = _break_glass_detail(status)
    elif not allow:
        detail = (
            f"{ALLOW_LIST_ENV} has no valid entries (defaults are "
            "npx,bunx,uvx,pipx); set it to include the binary or run "
            f"`mcp-gway local-unrestricted enable` with {UNRESTRICTED_ENV}=1"
        )
    else:
        detail = (
            f"add to {ALLOW_LIST_ENV} or run `mcp-gway local-unrestricted enable` "
            f"with {UNRESTRICTED_ENV}=1"
        )
    return PolicyDecision(
        allowed=False,
        reason_code="not_allowlisted",
        message=_not_allowlisted_message(basename, detail),
    )


def check_local_command(
    command: list[str] | None,
    *,
    host_loopback: bool = True,
    require_binary: bool = True,
) -> PolicyDecision:
    if not command:
        return PolicyDecision(
            allowed=False,
            reason_code="invalid_syntax",
            message="'command' required for type=local [reason=invalid_syntax]",
        )
    try:
        basename = validate_command_syntax(command)
    except ValueError as e:
        return PolicyDecision(
            allowed=False, reason_code="invalid_syntax", message=str(e)
        )
    gate = check_basename_allowed(basename, host_loopback=host_loopback)
    if not gate.allowed:
        return gate
    if require_binary:
        resolved = resolve_binary(basename)
        if not resolved:
            return PolicyDecision(
                allowed=False,
                reason_code="binary_not_found",
                message=(
                    f"binary not found in PATH: {basename} "
                    "(install it or fix PATH) [reason=binary_not_found]"
                ),
            )
    return PolicyDecision(
        allowed=True, reason_code=gate.reason_code, message=gate.message
    )


def check_cwd(cwd: str | None) -> str | None:
    if cwd is None:
        return None
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("cwd must be absolute path [reason=invalid_cwd]")
    p = Path(cwd.strip())
    if not p.is_absolute():
        raise ValueError("cwd must be absolute path [reason=invalid_cwd]")
    try:
        resolved = p.resolve()
    except Exception as e:
        raise ValueError("cwd cannot be resolved [reason=invalid_cwd]") from e
    if not resolved.is_dir():
        raise ValueError(f"cwd not a directory: {cwd} [reason=invalid_cwd]")
    return str(resolved)


def check_environment(env: dict[str, str] | None) -> dict[str, str] | None:
    if env is None:
        return None
    if not isinstance(env, dict):
        raise ValueError("environment must be a JSON object [reason=invalid_env]")  # noqa: TRY004
    for key in env:
        upper = str(key).upper()
        if upper in ENV_DENYLIST_EXACT or upper.startswith(ENV_DENYLIST_PREFIXES):
            raise ValueError(
                f"environment variable not allowed: {key} [reason=denied_env]"
            )
    return env


def audit_local_action(
    action: str, name: str, basename: str | None, decision: PolicyDecision
) -> None:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:50]
    safe_base = re.sub(r"[^A-Za-z0-9_.-]", "_", basename or "-")[:50]
    logger.info(
        "local action=%s name=%s binary=%s allowed=%s reason=%s",
        action,
        safe_name,
        safe_base,
        decision.allowed,
        decision.reason_code,
    )
