from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx


FETCH_TIMEOUT = 15.0
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_SNAPSHOT_CHARS = 60_000


class UnsafeURLError(ValueError):
    pass


@dataclass
class PageSnapshot:
    url: str
    final_url: str
    title: str
    domain: str
    content: str
    content_hash: str
    reader: str


class _ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.title_depth = 0
        self.title: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self.skip += 1
        if tag == "title":
            self.title_depth += 1
        if not self.skip and tag in {"p", "div", "article", "section", "li", "blockquote", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")
        if not self.skip and tag in {"h1", "h2", "h3", "h4"}:
            self.parts.append(f"{'#' * int(tag[1])} ")
        elif not self.skip and tag == "li":
            self.parts.append("- ")
        elif not self.skip and tag == "blockquote":
            self.parts.append("> ")

    def handle_endtag(self, tag: str):
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"} and self.skip:
            self.skip -= 1
        if not self.skip and tag in {"p", "div", "article", "section", "li", "blockquote", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if self.title_depth:
            self.title.append(data)
        if not self.skip:
            self.parts.append(data)

    def document(self) -> tuple[str, str]:
        text = html.unescape("".join(self.parts))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n(?:\s*\n)+", "\n\n", text).strip()
        return " ".join(self.title).strip(), text


def canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("Only public HTTP(S) URLs are supported")
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host if port is None or (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443) else f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def validate_public_url(url: str) -> str:
    normalized = canonical_url(url)
    host = urlsplit(normalized).hostname or ""
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise UnsafeURLError("The website hostname could not be resolved") from exc
    if not addresses:
        raise UnsafeURLError("The website hostname could not be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise UnsafeURLError("Private and local network addresses are not allowed")
    return normalized


def _response_bytes(response: httpx.Response) -> bytes:
    length = response.headers.get("content-length")
    if length and int(length) > MAX_RESPONSE_BYTES:
        raise ValueError("The web page is too large")
    content = response.content
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("The web page is too large")
    return content


def _extract(response: httpx.Response, final_url: str) -> tuple[str, str]:
    raw = _response_bytes(response)
    content_type = response.headers.get("content-type", "").lower()
    text = raw.decode(response.encoding or "utf-8", errors="replace")
    if "html" in content_type or "<html" in text[:500].lower():
        parser = _ReadableHTML()
        parser.feed(text)
        title, content = parser.document()
    elif "json" in content_type:
        title, content = urlsplit(final_url).hostname or final_url, text
    else:
        title, content = urlsplit(final_url).hostname or final_url, text
    content = content[:MAX_SNAPSHOT_CHARS].strip()
    if not content:
        raise ValueError("The web page did not contain readable text")
    return title or (urlsplit(final_url).hostname or final_url), content


def fetch_page(
    url: str,
    *,
    jina_fallback: bool = True,
    transport: httpx.BaseTransport | None = None,
    resolver=validate_public_url,
) -> PageSnapshot:
    original = resolver(url)
    current = original
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=False, transport=transport, headers={
            "User-Agent": "Bobodan/0.1 (+local learning assistant)",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }) as client:
            for _ in range(MAX_REDIRECTS + 1):
                response = client.get(current)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("The website returned an invalid redirect")
                    current = resolver(urljoin(current, location))
                    continue
                response.raise_for_status()
                title, content = _extract(response, current)
                return PageSnapshot(
                    url=original,
                    final_url=current,
                    title=title,
                    domain=urlsplit(current).hostname or "",
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    reader="direct",
                )
            raise ValueError("The website redirected too many times")
    except UnsafeURLError:
        raise
    except ValueError as exc:
        if not jina_fallback or any(token in str(exc).lower() for token in ("too large", "redirect")):
            raise
    except Exception:
        if not jina_fallback:
            raise

    jina_url = f"https://r.jina.ai/{original}"
    with httpx.Client(timeout=FETCH_TIMEOUT, transport=transport, headers={"Accept": "text/plain"}) as client:
        response = client.get(jina_url)
        response.raise_for_status()
        content = _response_bytes(response).decode(response.encoding or "utf-8", errors="replace")[:MAX_SNAPSHOT_CHARS].strip()
    if not content:
        raise ValueError("Jina Reader did not return readable text")
    title_match = re.search(r"^Title:\s*(.+)$", content, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else (urlsplit(original).hostname or original)
    return PageSnapshot(
        url=original,
        final_url=original,
        title=title,
        domain=urlsplit(original).hostname or "",
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        reader="jina",
    )


def evidence_excerpt(content: str, query: str, limit: int = 6000) -> str:
    paragraphs = [item.strip() for item in re.split(r"\n{2,}", content) if item.strip()]
    terms = {term.lower() for term in re.findall(r"[\w\u3400-\u9fff]{2,}", query)}
    ranked = sorted(
        enumerate(paragraphs),
        key=lambda item: (-sum(term in item[1].lower() for term in terms), item[0]),
    )
    selected: list[str] = []
    size = 0
    for _, paragraph in ranked:
        if size + len(paragraph) + 2 > limit and selected:
            continue
        selected.append(paragraph)
        size += len(paragraph) + 2
        if size >= limit:
            break
    return "\n\n".join(selected)[:limit]
