import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from .base import register_tool, ToolResult

MAX_RESPONSE_SIZE = 10 * 1024  # 10KB
ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
MAX_REDIRECTS = 5
BINARY_TYPES = {
    "image/", "video/", "audio/", "application/pdf", "application/zip",
    "application/gzip", "application/x-tar", "application/octet-stream",
    "application/vnd.", "font/",
}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, link-local, or multicast."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
    except ValueError:
        return True  # reject unparseable IPs


def _resolve_and_check_host(hostname: str, allow_private: bool) -> str | None:
    """Resolve hostname and check all resulting IPs. Returns error message or None."""
    if allow_private:
        return None
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip_str = info[4][0]
            if _is_private_ip(ip_str):
                return f"Access denied: {hostname} resolves to private/loopback address {ip_str}"
    except socket.gaierror:
        return None  # DNS failure will surface as connection error later
    return None


def _check_url(url: str, allow_private: bool) -> str | None:
    """Validate URL against SSRF rules. Returns error message or None."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if not allow_private:
        if hostname in ("localhost", "0.0.0.0"):
            return f"Access denied: {hostname} is a loopback address"

    return _resolve_and_check_host(hostname, allow_private)


def _is_binary_content(content_type: str) -> bool:
    """Check if Content-Type indicates binary content."""
    ct_lower = content_type.lower()
    return any(ct_lower.startswith(prefix) for prefix in BINARY_TYPES)


def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
    timeout: int = 30,
    allow_private_network: bool = False,
) -> ToolResult:
    """Send an HTTP request and return the response."""
    method = method.upper()
    if method not in ALLOWED_METHODS:
        return ToolResult(
            ok=False,
            content=f"Unsupported method: {method}. Allowed: {', '.join(sorted(ALLOWED_METHODS))}",
        )

    if not url.startswith(("http://", "https://")):
        return ToolResult(ok=False, content=f"Only http/https URLs are supported, got: {url}")

    # SSRF check on initial URL
    error = _check_url(url, allow_private_network)
    if error:
        return ToolResult(ok=False, content=error)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.request(method, url, headers=headers, content=body)

            # Manual redirect handling with SSRF re-check
            redirect_count = 0
            while resp.is_redirect and redirect_count < MAX_REDIRECTS:
                redirect_count += 1
                location = resp.headers.get("location", "")
                if not location:
                    break
                # Resolve relative redirects
                redirect_url = str(httpx.URL(url).join(location))
                error = _check_url(redirect_url, allow_private_network)
                if error:
                    return ToolResult(ok=False, content=f"Redirect blocked: {error}")
                resp = client.request(method, redirect_url, headers=headers, content=body)

            # Build response
            status_line = f"HTTP/{resp.http_version} {resp.status_code} {resp.reason_phrase}"
            content_type = resp.headers.get("content-type", "")

            # Headers summary
            header_lines = [status_line]
            for key in ("content-type", "content-length", "location"):
                val = resp.headers.get(key)
                if val:
                    header_lines.append(f"{key}: {val}")

            if _is_binary_content(content_type):
                body_text = f"Body omitted: binary response ({content_type}), {len(resp.content)} bytes"
            else:
                raw = resp.content
                if len(raw) > MAX_RESPONSE_SIZE:
                    body_text = raw[:MAX_RESPONSE_SIZE].decode("utf-8", errors="replace")
                    body_text += f"\n... [truncated, {len(raw)} bytes total]"
                else:
                    body_text = resp.text

            content = "\n".join(header_lines) + "\n\n" + body_text
            return ToolResult(ok=True, content=content, data={"status_code": resp.status_code})

    except httpx.TimeoutException:
        return ToolResult(ok=False, content=f"Request timed out after {timeout}s: {method} {url}")
    except httpx.ConnectError as e:
        return ToolResult(ok=False, content=f"Connection error: {e}")
    except Exception as e:
        return ToolResult(ok=False, content=f"HTTP request error: {e}")


register_tool(
    "http_request",
    "Send an HTTP request. Returns status line, headers, and response body (truncated to 10KB). "
    "Only http/https URLs are allowed. Private/loopback addresses are blocked by default.",
    {
        "type": "object",
        "properties": {
            "method": {"type": "string", "description": "HTTP method (GET/POST/PUT/DELETE/PATCH), default GET"},
            "url": {"type": "string", "description": "Full URL (http or https)"},
            "headers": {"type": "object", "description": "Request headers as key-value pairs"},
            "body": {"type": "string", "description": "Request body (for POST/PUT/PATCH)"},
            "timeout": {"type": "integer", "description": "Timeout in seconds, default 30"},
            "allow_private_network": {
                "type": "boolean",
                "description": "Allow requests to private/loopback addresses (default false)",
            },
        },
        "required": ["url"],
    },
    http_request,
)
