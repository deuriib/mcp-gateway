"""OAuth2 support for MCP servers requiring authentication."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import string
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx2
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)


class FileTokenStorage:
    """File-based token storage for OAuth tokens."""

    def __init__(self, server_name: str, storage_dir: Path | None = None) -> None:
        self._storage_dir = (
            storage_dir or Path.home() / ".config" / "mcp-gway" / "tokens"
        )
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._token_file = self._storage_dir / f"{server_name}.json"

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
            json.dumps(tokens.model_dump(exclude_none=True), indent=2),
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
            json.dumps(client_info.model_dump(exclude_none=True), indent=2),
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
        """Start the local callback server."""
        self._server = await asyncio.start_server(
            self._handle_request, "127.0.0.1", self._port
        )

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


async def discover_oauth_metadata(server_url: str) -> dict[str, Any] | None:
    """Discover OAuth metadata from the server.

    First checks Protected Resource Metadata (RFC 8707) for the authorization server,
    then discovers OAuth metadata from that server.
    """
    async with httpx2.AsyncClient() as client:
        # Step 1: Try to get Protected Resource Metadata
        parsed = urlparse(server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/mcp"

        prm_urls = [
            f"{base_url}/.well-known/oauth-protected-resource{path}",
            f"{base_url}/.well-known/oauth-protected-resource",
        ]

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
) -> httpx2.AsyncClient | None:
    """Run the full OAuth flow.

    Args:
        server_url: The MCP server URL
        server_name: Name of the server for storage
        client_metadata: Optional OAuth client metadata
        output_callback: Optional callback for output messages

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

    # Start callback server
    callback_server = OAuthCallbackServer(port=callback_port)
    await callback_server.start()

    # Dynamic client registration (RFC 7591)
    client_id = "mcp-gway"
    client_secret = None

    if registration_endpoint:
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
        "scope": "openid profile email",
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
