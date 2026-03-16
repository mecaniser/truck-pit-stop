from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.logging import get_logger
from app.services.cloudinary_service import is_cloudinary_configured, upload_tenant_logo

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; DieselBridgeLogoBot/1.0; "
    "+https://www.dieselbridge.com)"
)
MAX_REDIRECTS = 5
MAX_HTML_BYTES = 1_000_000
MAX_MANIFEST_BYTES = 500_000
MAX_IMAGE_BYTES = 5_000_000
DEFAULT_TIMEOUT = 8.0


@dataclass(frozen=True)
class LogoCandidate:
    url: str
    source: str
    priority: int
    size_hint: int = 0


@dataclass(frozen=True)
class WebsiteLogoParseResult:
    candidates: list[LogoCandidate]
    manifest_urls: list[str]


class _WebsiteMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_tags: list[dict[str, str]] = []
        self.link_tags: list[dict[str, str]] = []
        self.image_tags: list[dict[str, str]] = []
        self.json_ld_blocks: list[str] = []
        self._inside_json_ld = False
        self._json_ld_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_attrs = {
            key.lower(): value.strip()
            for key, value in attrs
            if key and isinstance(value, str) and value.strip()
        }
        tag = tag.lower()

        if tag == "meta":
            self.meta_tags.append(normalized_attrs)
        elif tag == "link":
            self.link_tags.append(normalized_attrs)
        elif tag == "img":
            self.image_tags.append(normalized_attrs)
        elif tag == "script" and normalized_attrs.get("type", "").lower() == "application/ld+json":
            self._inside_json_ld = True
            self._json_ld_chunks = []

    def handle_data(self, data: str) -> None:
        if self._inside_json_ld:
            self._json_ld_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._inside_json_ld:
            payload = "".join(self._json_ld_chunks).strip()
            if payload:
                self.json_ld_blocks.append(payload)
            self._inside_json_ld = False
            self._json_ld_chunks = []


def parse_website_logo_candidates(html: str, page_url: str) -> WebsiteLogoParseResult:
    parser = _WebsiteMetadataParser()
    parser.feed(html)

    deduped: dict[str, LogoCandidate] = {}
    manifest_urls: list[str] = []

    def add_candidate(url: str | None, source: str, priority: int, size_hint: int = 0) -> None:
        if not url:
            return
        absolute = _normalize_candidate_url(page_url, url)
        if not absolute:
            return

        candidate = LogoCandidate(
            url=absolute,
            source=source,
            priority=priority + min(size_hint, 1024),
            size_hint=size_hint,
        )
        existing = deduped.get(candidate.url)
        if existing is None or candidate.priority > existing.priority:
            deduped[candidate.url] = candidate

    for image_tag in parser.image_tags:
        for attr_name, image_url in _extract_image_urls(image_tag):
            priority = _score_image_candidate(image_tag, image_url)
            if priority > 0:
                add_candidate(image_url, f"img.logo.{attr_name}", priority)

    for meta_tag in parser.meta_tags:
        key = (meta_tag.get("property") or meta_tag.get("name") or meta_tag.get("itemprop") or "").lower()
        content = meta_tag.get("content")
        if not content:
            continue
        if key in {"logo", "og:logo"}:
            add_candidate(content, f"meta.{key}", 480)
        elif key == "itemprop" and meta_tag.get("itemprop", "").lower() == "logo":
            add_candidate(content, "meta.itemprop.logo", 480)
        elif key in {"twitter:image", "twitter:image:src"}:
            add_candidate(content, f"meta.{key}", 180)
        elif key in {"og:image", "og:image:url", "og:image:secure_url"}:
            add_candidate(content, f"meta.{key}", 160)
        elif key == "msapplication-tileimage":
            add_candidate(content, "meta.tileimage", 220)

    for link_tag in parser.link_tags:
        href = link_tag.get("href")
        if not href:
            continue
        rel_tokens = {token.lower() for token in link_tag.get("rel", "").split()}
        size_hint = _parse_size_hint(link_tag.get("sizes"))
        if "manifest" in rel_tokens:
            manifest_url = _normalize_candidate_url(page_url, href)
            if manifest_url:
                manifest_urls.append(manifest_url)
            continue
        if "apple-touch-icon" in rel_tokens or "apple-touch-icon-precomposed" in rel_tokens:
            add_candidate(href, "link.apple-touch-icon", 320, size_hint)
            continue
        if "icon" in rel_tokens or ("shortcut" in rel_tokens and "icon" in href.lower()):
            add_candidate(href, "link.icon", 240, size_hint)
            continue
        if "mask-icon" in rel_tokens:
            add_candidate(href, "link.mask-icon", 200, size_hint)

    for raw_json in parser.json_ld_blocks:
        for logo_url in _extract_logo_urls_from_json_ld(raw_json, page_url):
            add_candidate(logo_url, "jsonld.logo", 460)

    add_candidate("/favicon.ico", "fallback.favicon", 20)

    candidates = sorted(
        deduped.values(),
        key=lambda candidate: (-candidate.priority, candidate.url),
    )
    manifest_urls = sorted(set(manifest_urls))
    return WebsiteLogoParseResult(candidates=candidates, manifest_urls=manifest_urls)


async def import_logo_from_website(website_url: str, tenant_id: str | None = None) -> str | None:
    normalized_website_url = _normalize_public_http_url(website_url)
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        page_url, html, _content_type = await _fetch_bytes(
            client,
            normalized_website_url,
            max_bytes=MAX_HTML_BYTES,
            expected_kind="html",
        )
        parsed = parse_website_logo_candidates(html.decode("utf-8", errors="ignore"), page_url)
        manifest_candidates = await _fetch_manifest_logo_candidates(client, parsed.manifest_urls)
        candidates = sorted(
            [*parsed.candidates, *manifest_candidates],
            key=lambda candidate: (-candidate.priority, candidate.url),
        )

        for candidate in candidates:
            try:
                final_url, image_bytes, content_type = await _fetch_bytes(
                    client,
                    candidate.url,
                    max_bytes=MAX_IMAGE_BYTES,
                    expected_kind="image",
                )
            except Exception as exc:
                logger.info(
                    "website_logo_candidate_failed",
                    website_url=normalized_website_url,
                    candidate_url=candidate.url,
                    source=candidate.source,
                    error=str(exc),
                )
                continue

            if is_cloudinary_configured() and tenant_id:
                try:
                    return await upload_tenant_logo(
                        image_bytes=image_bytes,
                        tenant_id=tenant_id,
                        content_type=content_type,
                        source_url=final_url,
                    )
                except Exception as exc:
                    logger.warning(
                        "website_logo_cloudinary_upload_failed",
                        tenant_id=tenant_id,
                        website_url=normalized_website_url,
                        candidate_url=final_url,
                        source=candidate.source,
                        error=str(exc),
                    )
            return final_url

    return None


async def _fetch_manifest_logo_candidates(
    client: httpx.AsyncClient,
    manifest_urls: list[str],
) -> list[LogoCandidate]:
    candidates: dict[str, LogoCandidate] = {}
    for manifest_url in manifest_urls:
        try:
            final_url, payload_bytes, _content_type = await _fetch_bytes(
                client,
                manifest_url,
                max_bytes=MAX_MANIFEST_BYTES,
                expected_kind="manifest",
            )
        except Exception as exc:
            logger.info("website_logo_manifest_fetch_failed", manifest_url=manifest_url, error=str(exc))
            continue

        try:
            payload = json.loads(payload_bytes.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            logger.info("website_logo_manifest_invalid_json", manifest_url=manifest_url)
            continue

        for icon in payload.get("icons", []) if isinstance(payload, dict) else []:
            if not isinstance(icon, dict):
                continue
            src = icon.get("src")
            if not isinstance(src, str) or not src.strip():
                continue
            absolute = _normalize_candidate_url(final_url, src)
            if not absolute:
                continue
            size_hint = _parse_size_hint(icon.get("sizes"))
            candidate = LogoCandidate(
                url=absolute,
                source="manifest.icon",
                priority=280 + min(size_hint, 1024),
                size_hint=size_hint,
            )
            existing = candidates.get(candidate.url)
            if existing is None or candidate.priority > existing.priority:
                candidates[candidate.url] = candidate

    return list(candidates.values())


async def _fetch_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
    expected_kind: str,
) -> tuple[str, bytes, str]:
    current_url = _normalize_public_http_url(url)

    for _redirect_index in range(MAX_REDIRECTS + 1):
        await _ensure_public_url(current_url)
        async with client.stream(
            "GET",
            current_url,
            follow_redirects=False,
            headers={"Accept": _accept_header(expected_kind)},
        ) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                redirect_location = response.headers.get("location")
                if not redirect_location:
                    raise ValueError("Redirect response did not include a location")
                current_url = urljoin(str(response.url), redirect_location)
                continue

            response.raise_for_status()
            payload = await _read_limited_body(response, max_bytes)
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            final_url = str(response.url)
            _validate_response_kind(expected_kind, final_url, content_type, payload)
            return final_url, payload, content_type or "application/octet-stream"

    raise ValueError("Too many redirects while fetching website logo")


async def _read_limited_body(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in response.aiter_bytes():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise ValueError(f"Response exceeded {max_bytes} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_response_kind(expected_kind: str, url: str, content_type: str, payload: bytes) -> None:
    lower_url = url.lower()
    if expected_kind == "html":
        if content_type and ("html" in content_type or "xml" in content_type):
            return
        if payload.lstrip().startswith((b"<!doctype html", b"<html", b"<?xml")):
            return
        raise ValueError("Website did not return HTML content")

    if expected_kind == "manifest":
        if content_type in {"application/manifest+json", "application/json"}:
            return
        if payload.lstrip().startswith((b"{", b"[")):
            return
        raise ValueError("Manifest did not return JSON content")

    if expected_kind == "image":
        if content_type.startswith("image/"):
            return
        if lower_url.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".ico", ".avif")):
            return
        if payload.lstrip().startswith(b"<svg"):
            return
        raise ValueError("Candidate did not return image content")

    raise ValueError(f"Unsupported expected content kind: {expected_kind}")


def _accept_header(expected_kind: str) -> str:
    if expected_kind == "html":
        return "text/html,application/xhtml+xml"
    if expected_kind == "manifest":
        return "application/manifest+json,application/json,text/plain"
    if expected_kind == "image":
        return "image/*,*/*;q=0.8"
    return "*/*"


def _normalize_candidate_url(base_url: str, raw_url: str) -> str | None:
    candidate = raw_url.strip()
    if not candidate or candidate.startswith("data:"):
        return None
    return urljoin(base_url, candidate)


def _normalize_public_http_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    if not candidate:
        raise ValueError("Website URL is required")
    parsed = urlparse(candidate)
    if not parsed.scheme:
        parsed = urlparse(f"https://{candidate}")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https websites are supported")
    if not parsed.hostname:
        raise ValueError("Website URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("Website URL must not include credentials")
    return parsed.geturl()


async def _ensure_public_url(raw_url: str) -> None:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http/https URLs are allowed")

    hostname = parsed.hostname
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        addrinfo = await asyncio.to_thread(socket.getaddrinfo, hostname, None, type=socket.SOCK_STREAM)
        addresses = []
        for entry in addrinfo:
            sockaddr = entry[4]
            if not sockaddr:
                continue
            addresses.append(ipaddress.ip_address(sockaddr[0]))

    if not addresses:
        raise ValueError("Unable to resolve website host")

    for address in addresses:
        if not address.is_global:
            raise ValueError("Private or local network addresses are not allowed")


def _parse_size_hint(raw_sizes: Any) -> int:
    if not raw_sizes:
        return 0
    if isinstance(raw_sizes, str):
        best = 0
        for token in raw_sizes.lower().split():
            if token == "any":
                best = max(best, 1024)
                continue
            width, separator, height = token.partition("x")
            if separator and width.isdigit() and height.isdigit():
                best = max(best, max(int(width), int(height)))
        return best
    return 0


def _extract_image_urls(image_tag: dict[str, str]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_url(attr_name: str, raw_url: str | None) -> None:
        if not raw_url:
            return
        candidate = raw_url.strip()
        if not candidate or candidate in seen:
            return
        seen.add(candidate)
        urls.append((attr_name, candidate))

    for attr_name in (
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-orig-file",
        "data-large-file",
        "data-medium-file",
        "src",
    ):
        add_url(attr_name, image_tag.get(attr_name))

    for attr_name in ("data-srcset", "srcset"):
        srcset_url = _parse_srcset_url(image_tag.get(attr_name))
        if srcset_url:
            add_url(attr_name, srcset_url)

    return urls


def _parse_srcset_url(raw_srcset: str | None) -> str | None:
    if not raw_srcset:
        return None
    first_candidate = raw_srcset.split(",", 1)[0].strip()
    if not first_candidate:
        return None
    return first_candidate.split()[0].strip() or None


def _score_image_candidate(image_tag: dict[str, str], image_url: str) -> int:
    alt = image_tag.get("alt", "").lower()
    class_name = image_tag.get("class", "").lower()
    element_id = image_tag.get("id", "").lower()
    data_widget_type = image_tag.get("data-widget_type", "").lower()
    data_element_type = image_tag.get("data-element_type", "").lower()
    image_path = urlparse(image_url).path.lower()

    context = " ".join(
        value
        for value in (alt, class_name, element_id, data_widget_type, data_element_type)
        if value
    )

    priority = 0

    strong_logo_tokens = (
        "site-logo",
        "custom-logo",
        "header-logo",
        "logo-light",
        "logo-dark",
        "brand-logo",
        "navbar-brand",
        "pxl_logo",
        "widget_pxl_logo",
    )
    if any(token in context for token in strong_logo_tokens):
        priority = max(priority, 700)
    elif "logo" in class_name or "logo" in element_id:
        priority = max(priority, 620)

    if "logo" in alt:
        priority = max(priority, 560)

    if _looks_like_logo_filename(image_path):
        priority = max(priority, 260)

    width = _safe_int(image_tag.get("width"))
    height = _safe_int(image_tag.get("height"))
    if width and height and height > 0:
        aspect_ratio = width / height
        if aspect_ratio >= 2.0:
            priority += 80
        elif aspect_ratio >= 1.4:
            priority += 40

    return priority


def _looks_like_logo_filename(image_path: str) -> bool:
    filename = image_path.rsplit("/", 1)[-1]
    return any(token in filename for token in ("logo", "brandmark", "wordmark"))


def _safe_int(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    digits = "".join(ch for ch in raw_value if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _extract_logo_urls_from_json_ld(raw_json: str, page_url: str) -> list[str]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    urls: list[str] = []

    def add_if_url(value: Any) -> None:
        if isinstance(value, str):
            absolute = _normalize_candidate_url(page_url, value)
            if absolute:
                urls.append(absolute)
        elif isinstance(value, dict):
            for key in ("url", "contentUrl", "@id"):
                nested = value.get(key)
                if isinstance(nested, str):
                    absolute = _normalize_candidate_url(page_url, nested)
                    if absolute:
                        urls.append(absolute)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() == "logo":
                    add_if_url(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return urls
