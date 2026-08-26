"""OAuth2 support for MCP servers requiring authentication."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
import string
import uuid
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

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


def _validate_server_name(name: str) -> None:
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError("Invalid server name")
    if not name.isascii():
        raise ValueError("Name must contain only ASCII characters")
    if "-" in name or " " in name:
        raise ValueError("Name cannot contain hyphens or spaces")
    if name and name[0].isdigit():
        raise ValueError("Name cannot start with a number")
    if "<" in name or ">" in name:
        raise ValueError("Name contains invalid characters")
    if not _NAME_RE.match(name):
        raise ValueError("Name must match ^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    if name.lower() in _RESERVED_NAMES:
        raise ValueError("Name is reserved")


import httpx2
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)


class FileTokenStorage:
    """File-based token storage for OAuth tokens."""

    def __init__(self, server_name: str, storage_dir: Path | None = None) -> None:
        _validate_server_name(server_name)
        self._storage_dir = (
            storage_dir or Path.home() / ".config" / "mcp-gway" / "tokens"
        )
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        token_path = self._storage_dir / f"{server_name}.json"
        try:
            if not token_path.resolve().is_relative_to(self._storage_dir.resolve()):
                raise ValueError("Invalid server name: path traversal")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError("Invalid server name") from e
        self._token_file = token_path

    async def get_tokens(self) -> OAuthToken | None:
        if not self._token_file.exists():
            return None
        try:
            data = json.loads(self._token_file.read_text(encoding="utf-8"))
            return OAuthToken(**data)
        except Exception:
            return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._token_file.write_text(
            json.dumps(tokens.model_dump(mode="json", exclude_none=True), indent=2),
            encoding="utf-8",
        )

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        info_file = self._storage_dir / f"{self._token_file.stem}_client.json"
        if not info_file.exists():
            return None
        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
            return OAuthClientInformationFull(**data)
        except Exception:
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        info_file = self._storage_dir / f"{self._token_file.stem}_client.json"
        info_file.write_text(
            json.dumps(
                client_info.model_dump(mode="json", exclude_none=True), indent=2
            ),
            encoding="utf-8",
        )


class OAuthCallbackServer:
    """Local HTTP server to handle OAuth callbacks."""

    def __init__(self, port: int = 8989) -> None:
        self._port = port
        self._server: asyncio.AbstractServer | None = None
        self._result: dict[str, str] | None = None
        self._event = asyncio.Event()

    async def _handle_request(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single HTTP request."""
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=5.0)
            if not data:
                return

            request_line = data.split(b"\r\n")[0].decode("utf-8", errors="replace")
            parts = request_line.split(" ")
            if len(parts) < 2:
                return

            path = parts[1]
            if "?" in path:
                _, query_string = path.split("?", 1)
                params = parse_qs(query_string)
            else:
                params = {}

            # Extract code and state from callback
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]

            if code:
                self._result = {"code": code, "state": state or ""}
                self._event.set()

                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: text/html\r\n"
                    "\r\n"
                    "<html><body>"
                    "<h1>Authentication successful!</h1>"
                    "<p>You can close this window and return to the terminal.</p>"
                    "</body></html>"
                )
            else:
                response = (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: text/html\r\n"
                    "\r\n"
                    "<html><body><h1>No authorization code received</h1></body></html>"
                )

            writer.write(response.encode())
            await writer.drain()
        except Exception:  # noqa: S110
            pass
        finally:
            writer.close()

    async def start(self) -> None:
        """Start the local callback server, trying next ports if busy."""
        last_exc = None
        for try_port in [self._port, self._port + 1, self._port + 2, 0]:
            try:
                self._server = await asyncio.start_server(
                    self._handle_request, "127.0.0.1", try_port
                )
                if try_port == 0 and self._server.sockets:
                    self._port = self._server.sockets[0].getsockname()[1]
                elif try_port != self._port:
                    self._port = try_port
                return
            except OSError as e:
                last_exc = e
                if (
                    getattr(e, "winerror", None) == 10048
                    or "already in use" in str(e).lower()
                    or "address already in use" in str(e).lower()
                ):
                    continue
                raise
        if last_exc:
            raise last_exc

    async def wait_for_callback(self, timeout: float = 300.0) -> dict[str, str] | None:
        """Wait for the OAuth callback."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return self._result
        except TimeoutError:
            return None
        finally:
            if self._server:
                self._server.close()
                await self._server.wait_closed()

    @property
    def callback_url(self) -> str:
        return f"http://127.0.0.1:{self._port}/callback"


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = "".join(
        secrets.choice(string.ascii_letters + string.digits + "-._~")
        for _ in range(128)
    )
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = __import__("base64").urlsafe_b64encode(digest).decode().rstrip("=")
    return code_verifier, code_challenge


def _parse_resource_metadata_url(www_auth: str) -> str | None:
    """Extract resource_metadata URL from WWW-Authenticate header per RFC 8707."""
    if not www_auth:
        return None
    m = re.search(r'resource_metadata\s*=\s*"([^"]+)"', www_auth)
    if m:
        return m.group(1)
    m2 = re.search(r"resource_metadata\s*=\s*'([^']+)'", www_auth)
    if m2:
        return m2.group(1)
    m3 = re.search(r"resource_metadata\s*=\s*([^\s,;]+)", www_auth)
    if m3:
        return m3.group(1).strip("\"'")
    return None


async def discover_oauth_metadata(server_url: str) -> dict[str, Any] | None:
    """Discover OAuth metadata from the server.

    First checks Protected Resource Metadata (RFC 8707) for the authorization server,
    then discovers OAuth metadata from that server. Supports WWW-Authenticate
    header with resource_metadata per MCP spec.
    """
    async with httpx2.AsyncClient(timeout=8.0) as client:
        # Step 0: Try WWW-Authenticate header from 401 as per MCP OAuth spec
        prm_from_header: str | None = None
        try:
            resp = await client.get(server_url, follow_redirects=True)
            if resp.status_code == 401:
                www_auth = resp.headers.get("www-authenticate", "") or resp.headers.get(
                    "WWW-Authenticate", ""
                )
                prm_from_header = _parse_resource_metadata_url(www_auth)
        except Exception:  # noqa: S112
            pass

        # Step 1: Try to get Protected Resource Metadata
        parsed = urlparse(server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/mcp"

        prm_urls: list[str] = []
        if prm_from_header:
            prm_urls.append(prm_from_header)
        prm_urls.extend(
            [
                f"{base_url}/.well-known/oauth-protected-resource{path}",
                f"{base_url}/.well-known/oauth-protected-resource",
            ]
        )

        auth_server_url = None
        for url in prm_urls:
            try:
                response = await client.get(url, follow_redirects=True)
                if response.status_code == 200:
                    prm = response.json()
                    auth_servers = prm.get("authorization_servers", [])
                    if auth_servers:
                        auth_server_url = auth_servers[0]
                        break
            except Exception:  # noqa: S112
                continue

        # Step 2: Discover OAuth metadata from authorization server
        if auth_server_url:
            discovery_urls = [
                f"{auth_server_url}/.well-known/oauth-authorization-server",
                f"{auth_server_url}/.well-known/openid-configuration",
            ]
        else:
            # Fallback to standard discovery on the server URL
            discovery_urls = [
                f"{base_url}/.well-known/oauth-authorization-server",
                f"{base_url}/.well-known/openid-configuration",
            ]

        for url in discovery_urls:
            try:
                response = await client.get(url, follow_redirects=True)
                if response.status_code == 200:
                    return response.json()
            except Exception:  # noqa: S112
                continue

    return None


async def run_oauth_flow(
    server_url: str,
    server_name: str,
    client_metadata: OAuthClientMetadata | None = None,
    output_callback: Any = None,
    callback_port: int = 8989,
    oauth_config: Any | None = None,
) -> httpx2.AsyncClient | None:
    """Run the full OAuth flow.

    Supports both manual (pre-registered clientId/secret) and autodiscovery
    (dynamic registration RFC 7591). If oauth_config contains a valid clientId,
    manual mode is used and registration is skipped.

    Args:
        server_url: The MCP server URL
        server_name: Name of the server for storage
        client_metadata: Optional OAuth client metadata
        output_callback: Optional callback for output messages
        callback_port: Local port for OAuth callback
        oauth_config: Optional OAuthConfig dict/object with clientId/clientSecret/scope

    Returns:
        Authenticated httpx client or None if flow fails
    """
    if output_callback is None:
        output_callback = lambda msg: None

    storage = FileTokenStorage(server_name)

    # Check for existing valid tokens
    existing_tokens = await storage.get_tokens()
    if existing_tokens and existing_tokens.access_token:
        output_callback("Using existing token...")
        return httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {existing_tokens.access_token}"}
        )

    # Discover OAuth metadata
    output_callback(f"Discovering OAuth metadata for {server_url}...")
    metadata = await discover_oauth_metadata(server_url)

    if not metadata:
        output_callback("Warning: Could not discover OAuth metadata.")
        output_callback("Please provide a token manually:")
        output_callback(
            f'  echo \'{{"access_token": "YOUR_TOKEN"}}\' > ~/.config/mcp-gway/tokens/{server_name}.json'
        )
        return None

    # Get endpoints
    auth_endpoint = metadata.get("authorization_endpoint")
    token_endpoint = metadata.get("token_endpoint")
    registration_endpoint = metadata.get("registration_endpoint")

    if not auth_endpoint or not token_endpoint:
        output_callback("Error: Missing authorization or token endpoint in metadata.")
        return None

    # Generate PKCE parameters
    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(32)

    def _extract_credentials(cfg: Any) -> tuple[str | None, str | None, str | None]:
        if cfg is None:
            return None, None, None
        if isinstance(cfg, dict):
            return (
                cfg.get("clientId") or cfg.get("client_id"),
                cfg.get("clientSecret") or cfg.get("client_secret"),
                cfg.get("scope"),
            )
        cid = getattr(cfg, "clientId", None) or getattr(cfg, "client_id", None)
        csec = getattr(cfg, "clientSecret", None) or getattr(cfg, "client_secret", None)
        sc = getattr(cfg, "scope", None)
        return cid, csec, sc

    oauth_cid, oauth_csec, oauth_scope = _extract_credentials(oauth_config)
    # also consider client_metadata scope
    meta_scope = getattr(client_metadata, "scope", None) if client_metadata else None
    effective_scope = oauth_scope or meta_scope or "openid profile email"

    is_manual = False
    if oauth_cid:
        try:
            uuid.UUID(str(oauth_cid))
            is_manual = True
        except Exception:
            oauth_cid = None

    # Start callback server
    callback_server = OAuthCallbackServer(port=callback_port)
    await callback_server.start()

    # Client credentials: manual takes precedence, else dynamic registration
    if is_manual:
        client_id = str(oauth_cid)
        client_secret = oauth_csec
        output_callback(f"Using pre-registered client: {client_id[:16]}... (manual)")
    else:
        client_id = str(uuid.uuid4())
        client_secret = None

    if not is_manual and registration_endpoint:
        output_callback("Registering OAuth client...")
        async with httpx2.AsyncClient() as http:
            reg_request = {
                "client_name": "MCP Gateway",
                "redirect_uris": [callback_server.callback_url],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            }
            try:
                reg_response = await http.post(
                    registration_endpoint,
                    json=reg_request,
                    headers={"Content-Type": "application/json"},
                )
                if reg_response.status_code in (200, 201):
                    reg_data = reg_response.json()
                    client_id = reg_data.get("client_id", client_id)
                    client_secret = reg_data.get("client_secret")
                    await storage.set_client_info(
                        OAuthClientInformationFull(
                            client_id=client_id,
                            client_secret=client_secret,
                            **{
                                k: v
                                for k, v in reg_data.items()
                                if k not in ("client_id", "client_secret")
                            },
                        )
                    )
                    output_callback(f"Registered client: {client_id[:16]}...")
                else:
                    output_callback(
                        f"Warning: Client registration failed ({reg_response.status_code}), using default client_id"
                    )
            except Exception as e:
                output_callback(
                    f"Warning: Client registration failed: {e}, using default client_id"
                )

    # Build authorization URL
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback_server.callback_url,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": effective_scope,
    }

    auth_url = f"{auth_endpoint}?{urlencode(auth_params)}"

    output_callback("Opening browser for authentication...")
    output_callback(f"If the browser doesn't open, visit:\n{auth_url}")

    # Open browser
    webbrowser.open(auth_url)

    # Wait for callback
    output_callback("Waiting for authentication callback...")
    callback_result = await callback_server.wait_for_callback(timeout=300.0)

    if not callback_result or not callback_result.get("code"):
        output_callback("Error: Authentication timed out or no code received.")
        return None

    # Exchange code for tokens
    output_callback("Exchanging authorization code for tokens...")

    token_data = {
        "grant_type": "authorization_code",
        "code": callback_result["code"],
        "redirect_uri": callback_server.callback_url,
        "code_verifier": code_verifier,
        "client_id": client_id,
    }

    if client_secret:
        token_data["client_secret"] = client_secret

    async with httpx2.AsyncClient() as client:
        try:
            response = await client.post(
                token_endpoint,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                token_response = response.json()
                tokens = OAuthToken(
                    access_token=token_response.get("access_token", ""),
                    token_type=token_response.get("token_type", "Bearer"),
                    refresh_token=token_response.get("refresh_token"),
                    expires_in=token_response.get("expires_in"),
                )
                await storage.set_tokens(tokens)
                output_callback("Authentication successful!")

                return httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {tokens.access_token}"}
                )
            else:
                output_callback(
                    f"Error: Token exchange failed with status {response.status_code}"
                )
                output_callback(f"Response: {response.text[:200]}")
                return None

        except Exception as e:
            output_callback(f"Error during token exchange: {e}")
            return None


async def get_authenticated_client(server_name: str) -> httpx2.AsyncClient | None:
    """Get an authenticated httpx client if tokens exist.

    Returns an authenticated httpx client or None if no tokens are available.
    """
    storage = FileTokenStorage(server_name)
    tokens = await storage.get_tokens()

    if tokens and tokens.access_token:
        return httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {tokens.access_token}"}
        )
    return None


_pending_oauth_flows: dict[str, dict[str, Any]] = {}


async def initiate_web_oauth(
    server_url: str,
    server_name: str,
    client_metadata: OAuthClientMetadata | None = None,
    callback_port: int = 8989,
    oauth_config: Any | None = None,
) -> tuple[str | None, str | None]:
    """Initiate OAuth flow for web dashboard - returns auth URL without blocking.

    Supports manual (pre-registered) vs autodiscovery (dynamic). If oauth_config
    contains a valid clientId, manual mode is used.

    Starts the callback server and registration, builds the auth URL, and
    launches a background task to wait for the callback and complete the flow.

    Returns (auth_url, error) - one will be set.
    """
    _validate_server_name(server_name)
    storage = FileTokenStorage(server_name)

    existing_tokens = await storage.get_tokens()
    if existing_tokens and existing_tokens.access_token:
        return None, "Already authenticated"

    metadata = await discover_oauth_metadata(server_url)
    if not metadata:
        return None, "Could not discover OAuth metadata"

    auth_endpoint = metadata.get("authorization_endpoint")
    token_endpoint = metadata.get("token_endpoint")
    registration_endpoint = metadata.get("registration_endpoint")

    if not auth_endpoint or not token_endpoint:
        return None, "Missing authorization or token endpoint"

    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(32)

    def _extract_credentials_web(cfg: Any) -> tuple[str | None, str | None, str | None]:
        if cfg is None:
            return None, None, None
        if isinstance(cfg, dict):
            return (
                cfg.get("clientId") or cfg.get("client_id"),
                cfg.get("clientSecret") or cfg.get("client_secret"),
                cfg.get("scope"),
            )
        cid = getattr(cfg, "clientId", None) or getattr(cfg, "client_id", None)
        csec = getattr(cfg, "clientSecret", None) or getattr(cfg, "client_secret", None)
        sc = getattr(cfg, "scope", None)
        return cid, csec, sc

    oauth_cid, oauth_csec, oauth_scope = _extract_credentials_web(oauth_config)
    meta_scope = getattr(client_metadata, "scope", None) if client_metadata else None
    effective_scope = oauth_scope or meta_scope or "openid profile email"

    is_manual = False
    if oauth_cid:
        try:
            uuid.UUID(str(oauth_cid))
            is_manual = True
        except Exception:
            oauth_cid = None

    callback_server = OAuthCallbackServer(port=callback_port)
    try:
        await callback_server.start()
    except Exception as e:
        return None, f"Could not start callback server: {e}"

    if is_manual:
        client_id = str(oauth_cid)
        client_secret = oauth_csec
    else:
        client_id = str(uuid.uuid4())
        client_secret = None

    if not is_manual and registration_endpoint:
        try:
            async with httpx2.AsyncClient() as http:
                reg_request = {
                    "client_name": "MCP Gateway",
                    "redirect_uris": [callback_server.callback_url],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                }
                reg_response = await http.post(
                    registration_endpoint,
                    json=reg_request,
                    headers={"Content-Type": "application/json"},
                )
                if reg_response.status_code in (200, 201):
                    reg_data = reg_response.json()
                    client_id = reg_data.get("client_id", client_id)
                    client_secret = reg_data.get("client_secret")
                    try:
                        await storage.set_client_info(
                            OAuthClientInformationFull(
                                client_id=client_id,
                                client_secret=client_secret,
                                **{
                                    k: v
                                    for k, v in reg_data.items()
                                    if k not in ("client_id", "client_secret")
                                },
                            )
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    scope = effective_scope

    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": callback_server.callback_url,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": scope,
    }

    auth_url = f"{auth_endpoint}?{urlencode(auth_params)}"

    _pending_oauth_flows[server_name] = {
        "server_url": server_url,
        "state": state,
        "code_verifier": code_verifier,
        "client_id": client_id,
        "client_secret": client_secret,
        "token_endpoint": token_endpoint,
        "callback_server": callback_server,
        "storage": storage,
    }

    import asyncio as _asyncio

    _asyncio.create_task(_complete_web_oauth(server_name))

    return auth_url, None


async def _complete_web_oauth(server_name: str) -> None:
    flow = _pending_oauth_flows.get(server_name)
    if not flow:
        return
    callback_server: OAuthCallbackServer = flow["callback_server"]
    storage: FileTokenStorage = flow["storage"]
    try:
        result = await callback_server.wait_for_callback(timeout=300.0)
        if not result or not result.get("code"):
            _pending_oauth_flows.pop(server_name, None)
            return
        if result.get("state") != flow["state"]:
            _pending_oauth_flows.pop(server_name, None)
            return

        token_data = {
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": callback_server.callback_url,
            "code_verifier": flow["code_verifier"],
            "client_id": flow["client_id"],
        }
        if flow["client_secret"]:
            token_data["client_secret"] = flow["client_secret"]

        async with httpx2.AsyncClient() as http:
            resp = await http.post(
                flow["token_endpoint"],
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                data = resp.json()
                tokens = OAuthToken(
                    access_token=data.get("access_token", ""),
                    token_type=data.get("token_type", "Bearer"),
                    refresh_token=data.get("refresh_token"),
                    expires_in=data.get("expires_in"),
                )
                await storage.set_tokens(tokens)
                try:
                    from pathlib import Path as _Path

                    from mcp_gway.cli import _discover_tools as _cli_discover
                    from mcp_gway.registry import Registry

                    reg = Registry(
                        servers_dir=_Path.home() / ".config" / "mcp-gway" / "servers"
                    )
                    cfg = reg.get_config(server_name)
                    tools = await _cli_discover(cfg, force_auth=True)
                    if tools:
                        reg.update(server_name, tools)
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        _pending_oauth_flows.pop(server_name, None)


def get_pending_oauth_status(server_name: str) -> str:
    if server_name in _pending_oauth_flows:
        return "pending"
    return "none"
