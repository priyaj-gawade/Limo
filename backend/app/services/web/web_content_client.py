"""Direct Web Content Client (Phase D8.9).

Provides robust, multi-tier web extraction without Docker or external hosted scraping services.
Deployment-ready for single low-cost AWS EC2 instances.

Extraction Architecture:
1. Tier 1 (Default): Fast SSRF-safe HTTP retrieval + Trafilatura for article parsing.
2. Tier 2 (Dynamic JS Fallback): Crawl4AI (headless browser via Playwright) for heavy SPA/JS pages.
3. Tier 3 (Resilient Fallback): In-process BeautifulSoup HTML parser if dynamic engine is unavailable.

Strictly tags provenance: 'trafilatura' | 'crawl4ai' | 'fallback'.
SSRF boundaries are enforced on all URLs before network requests or browser navigation.
"""

import logging
import os
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from ...config import settings
from ...exceptions import StorageError
from ..extraction.ssrf import (
    SSRFProtectionError,
    fetch_url_ssrf_safe,
    validate_url,
)
from .models import ScrapeResult

logger = logging.getLogger("limo.services.web.content_client")

# Quality threshold: clean text must be at least 250 chars
MIN_ARTICLE_CHAR_COUNT = 250

# Obvious JS challenge/bot block markers indicating client-side rendering or protection
JS_CHALLENGE_PATTERNS = [
    re.compile(r"enable\s+javascript", re.IGNORECASE),
    re.compile(r"you\s+need\s+to\s+enable\s+javascript", re.IGNORECASE),
    re.compile(r"javascript\s+is\s+required", re.IGNORECASE),
    re.compile(r"attention\s+required!\s+\|\s+cloudflare", re.IGNORECASE),
    re.compile(r"checking\s+your\s+browser", re.IGNORECASE),
    re.compile(r"just\s+a\s+moment\.\.\.", re.IGNORECASE),
    re.compile(r"cf-browser-verification", re.IGNORECASE),
]


class WebContentClient:
    """Direct, Docker-free content client combining Trafilatura, Crawl4AI, and BeautifulSoup."""

    def __init__(self, timeout_sec: Optional[int] = None) -> None:
        self.timeout_sec = timeout_sec or getattr(settings, "web_crawl_timeout_sec", 15)

    async def scrape(self, url: str) -> ScrapeResult:
        """Extract article or webpage content with multi-tier resilience.

        1. SSRF pre-validation
        2. Tier 1: Fast HTTP + Trafilatura
        3. Tier 2: Crawl4AI dynamic browser fallback (if Tier 1 content is insufficient)
        4. Tier 3: In-process BeautifulSoup fallback (if Crawl4AI fails or unavailable)
        """
        clean_url = url.strip()
        if not clean_url:
            raise ValueError("URL to scrape cannot be empty")

        # 1. SSRF Pre-validation
        try:
            validate_url(clean_url)
        except SSRFProtectionError as e:
            logger.warning("SSRF blocked scrape attempt to '%s': %s", clean_url, str(e))
            raise

        start_time = time.perf_counter()

        # 2. Tier 1: Fast HTTP + Trafilatura
        raw_html: Optional[str] = None
        http_status: int = 200
        resp_headers: Dict[str, str] = {}

        try:
            resp = await fetch_url_ssrf_safe(clean_url, timeout_sec=float(self.timeout_sec))
            http_status = resp.status_code
            resp_headers = dict(resp.headers)
            raw_html = resp.content.decode("utf-8", errors="replace")

            if resp.status_code < 400 and raw_html:
                trafilatura_result = self._extract_with_trafilatura(clean_url, raw_html, start_time, resp.status_code, resp_headers)
                if trafilatura_result:
                    return trafilatura_result
        except SSRFProtectionError:
            raise
        except Exception as e:
            logger.info("Tier 1 HTTP fetch/trafilatura failed for '%s': %s. Trying Crawl4AI fallback.", clean_url, str(e))

        # 3. Tier 2: Crawl4AI Dynamic Browser Fallback
        crawl4ai_result = await self._extract_with_crawl4ai(clean_url, start_time)
        if crawl4ai_result:
            return crawl4ai_result

        # 4. Tier 3: In-Process BeautifulSoup Fallback
        if raw_html:
            return self._extract_with_beautifulsoup(clean_url, raw_html, start_time, http_status, resp_headers)

        # If raw_html was never obtained (e.g. initial connection failed and crawl4ai also failed),
        # raise informative error
        elapsed = round(time.perf_counter() - start_time, 3)
        raise StorageError(f"Failed to extract web content from '{clean_url}' across all tiers in {elapsed}s")

    def _extract_with_trafilatura(
        self,
        url: str,
        html: str,
        start_time: float,
        http_status: int,
        headers: Dict[str, str],
    ) -> Optional[ScrapeResult]:
        """Attempt extraction using Trafilatura."""
        try:
            import trafilatura  # type: ignore
        except ImportError:
            logger.debug("Trafilatura is not installed in Python environment")
            return None

        try:
            # Check for obvious JS challenge patterns first
            for pattern in JS_CHALLENGE_PATTERNS:
                if pattern.search(html[:5000]):
                    logger.info("JS challenge/rendering pattern detected in '%s'. Skipping Trafilatura.", url)
                    return None

            extracted_text = trafilatura.extract(
                html,
                url=url,
                include_links=True,
                include_images=False,
                include_comments=False,
                output_format="txt",
            )

            if not extracted_text or len(extracted_text.strip()) < MIN_ARTICLE_CHAR_COUNT:
                logger.info(
                    "Trafilatura extracted insufficient content (%d chars) for '%s'",
                    len(extracted_text.strip()) if extracted_text else 0,
                    url,
                )
                return None

            # Extract metadata (title, author, date)
            meta = trafilatura.extract_metadata(html, default_url=url)
            title = meta.title if meta and meta.title else ""
            if not title:
                # Fallback to simple title tag
                title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""

            elapsed = round(time.perf_counter() - start_time, 3)
            logger.info("Trafilatura successfully extracted '%s' in %.2fs (%d chars)", url, elapsed, len(extracted_text))

            source_meta: Dict[str, Any] = {
                "http_status": http_status,
                "content_type": headers.get("content-type", "text/html"),
            }
            if meta:
                if meta.author:
                    source_meta["author"] = meta.author
                if meta.date:
                    source_meta["date"] = meta.date
                if meta.description:
                    source_meta["description"] = meta.description
                if meta.sitename:
                    source_meta["sitename"] = meta.sitename

            return ScrapeResult(
                url=url,
                title=title,
                content=extracted_text.strip(),
                content_type="article",
                scrape_provider="trafilatura",
                http_status=http_status,
                elapsed_seconds=elapsed,
                source_metadata=source_meta,
            )
        except Exception as e:
            logger.warning("Trafilatura extraction threw error on '%s': %s", url, str(e))
            return None

    async def _ssrf_route_interceptor(self, route: Any, request: Any) -> None:
        """Playwright request interceptor that validates every network target against SSRF boundaries.

        Enforces SSRF boundaries on:
        - Initial page navigations
        - Dynamic redirects
        - Subresources (images, scripts, stylesheets, fonts, iframes)
        - In-page JavaScript network calls (fetch, XHR, WebSockets)

        Blocks:
        - loopback (127.0.0.1, ::1, localhost)
        - RFC1918 private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
        - cloud instance metadata (169.254.169.254)
        - non-HTTP/HTTPS schemes (file://, ftp://, gopher://)
        """
        req_url = getattr(request, "url", str(request))
        try:
            # Reuses authoritative validate_url in ssrf.py
            validate_url(req_url)
            await route.continue_()
        except SSRFProtectionError as se:
            logger.warning("Crawl4AI SSRF interceptor blocked browser request to '%s': %s", req_url, se)
            await route.abort("blockedbyclient")
        except Exception as ex:
            logger.warning("Crawl4AI SSRF interceptor blocked unverified request to '%s': %s", req_url, ex)
            await route.abort("blockedbyclient")

    async def _extract_with_crawl4ai(
        self,
        url: str,
        start_time: float,
    ) -> Optional[ScrapeResult]:
        """Attempt extraction using Crawl4AI (headless Playwright browser) with SSRF route interception."""
        try:
            from crawl4ai import AsyncWebCrawler  # type: ignore
        except ImportError:
            logger.debug("Crawl4AI is not installed in Python environment")
            return None

        try:
            logger.info("Attempting Crawl4AI dynamic browser extraction for '%s'", url)

            async def on_page_context_created(page: Any, *args: Any, **kwargs: Any) -> Any:
                # Intercept every subresource, navigation, XHR/fetch request from the page
                try:
                    await page.route("**/*", self._ssrf_route_interceptor)
                except Exception as ex:
                    logger.debug("Error setting up page route interceptor: %s", ex)
                return page

            async def before_goto(page: Any, *args: Any, **kwargs: Any) -> Any:
                # Defense-in-depth: pre-navigation validation
                target = kwargs.get("url") or (args[0] if args else url)
                if target:
                    validate_url(target)
                return page

            async with AsyncWebCrawler(verbose=False) as crawler:
                crawler.crawler_strategy.set_hook("on_page_context_created", on_page_context_created)
                crawler.crawler_strategy.set_hook("before_goto", before_goto)
                result = await crawler.arun(
                    url=url,
                    bypass_cache=True,
                    timeout=self.timeout_sec * 1000,
                )

                if not result or not result.success:
                    logger.warning("Crawl4AI crawl was not successful for '%s': %s", url, getattr(result, "error_message", "unknown"))
                    return None

                # Verify SSRF on any final redirected URL
                if getattr(result, "url", None) and result.url != url:
                    try:
                        validate_url(result.url)
                    except SSRFProtectionError as e:
                        logger.warning("Crawl4AI redirected to SSRF-violating URL '%s': %s", result.url, str(e))
                        return None

                content = ""
                # Crawl4AI provides result.markdown or markdown_v2
                if hasattr(result, "markdown") and result.markdown:
                    content = str(result.markdown).strip()
                elif hasattr(result, "cleaned_html") and result.cleaned_html:
                    content = str(result.cleaned_html).strip()

                if len(content) < MIN_ARTICLE_CHAR_COUNT:
                    logger.warning("Crawl4AI returned content below threshold (%d chars) for '%s'", len(content), url)
                    return None

                title = ""
                if hasattr(result, "metadata") and isinstance(result.metadata, dict):
                    title = result.metadata.get("title") or ""
                if not title and hasattr(result, "html") and result.html:
                    title_match = re.search(r"<title[^>]*>(.*?)</title>", result.html, re.IGNORECASE | re.DOTALL)
                    title = title_match.group(1).strip() if title_match else ""

                elapsed = round(time.perf_counter() - start_time, 3)
                logger.info("Crawl4AI successfully extracted '%s' in %.2fs (provider=crawl4ai)", url, elapsed)

                return ScrapeResult(
                    url=url,
                    title=title,
                    content=content,
                    content_type="article",
                    scrape_provider="crawl4ai",
                    http_status=getattr(result, "status_code", 200),
                    elapsed_seconds=elapsed,
                    source_metadata={
                        "rendered": True,
                        "redirected_url": getattr(result, "url", url),
                    },
                )
        except Exception as e:
            logger.warning("Crawl4AI execution failed for '%s': %s", url, str(e))
            return None

    def _extract_with_beautifulsoup(
        self,
        url: str,
        html: str,
        start_time: float,
        http_status: int,
        headers: Dict[str, str],
    ) -> ScrapeResult:
        """In-process BeautifulSoup parser used as resilient Tier 3 fallback."""
        soup = BeautifulSoup(html, "html.parser")

        # Strip non-content clutter
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "svg"]):
            tag.decompose()

        # Extract title
        title_tag = soup.find("title") or soup.find("h1")
        title = title_tag.get_text().strip() if title_tag else ""
        if not title:
            parsed = urllib.parse.urlparse(url)
            title = os.path.basename(parsed.path.rstrip("/")) or (parsed.hostname or "Article")

        # Extract main content body
        article_elem = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", class_=re.compile(r"content|article|body|post", re.I))
            or soup.body
        )
        body_elem = article_elem if article_elem else soup

        lines: List[str] = []
        if title:
            lines.append(f"# {title}\n")

        for child in body_elem.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
            text = child.get_text().strip()
            if not text or len(text) < 3:
                continue

            tag_name = child.name.lower()
            if tag_name == "h1":
                lines.append(f"\n# {text}\n")
            elif tag_name == "h2":
                lines.append(f"\n## {text}\n")
            elif tag_name == "h3":
                lines.append(f"\n### {text}\n")
            elif tag_name == "blockquote":
                lines.append(f"\n> {text}\n")
            elif tag_name == "li":
                lines.append(f"- {text}")
            else:
                lines.append(f"\n{text}\n")

        cleaned_markdown = "\n".join(lines).strip()
        elapsed = round(time.perf_counter() - start_time, 3)

        logger.info("BeautifulSoup fallback extractor scraped '%s' in %.2fs (provider=fallback)", url, elapsed)

        return ScrapeResult(
            url=url,
            title=title,
            content=cleaned_markdown,
            content_type="article",
            scrape_provider="fallback",
            http_status=http_status,
            elapsed_seconds=elapsed,
            source_metadata={
                "http_status": http_status,
                "content_type": headers.get("content-type", "text/html"),
                "fallback_reason": "Trafilatura and Crawl4AI yielded insufficient content or were bypassed",
            },
        )


# Global singleton instance
web_content_client = WebContentClient()
