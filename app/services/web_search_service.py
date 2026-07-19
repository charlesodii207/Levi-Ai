"""
web_search_service.py

Free web search using DuckDuckGo's HTML endpoint (no API key required).
This scrapes DuckDuckGo's lite/HTML search results page rather than using
a paid API (Google Custom Search, SerpAPI, Bing) — a reasonable tradeoff
while Levi AI is still pre-revenue. Swap this out for a paid API later
if result quality becomes a limiting factor; the calling code in chat.py
only depends on the shape of `search_web()`'s return value, not on how
results are actually fetched.
"""

import requests
from html import unescape
import re
from typing import Optional

SEARCH_URL = "https://html.duckduckgo.com/html/"

HEADERS = {
    # A normal browser User-Agent — DuckDuckGo's HTML endpoint is meant for
    # browsers without JS, but some basic bot-blocking still checks this.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT_SECONDS = 6


def _strip_tags(html_fragment: str) -> str:
    """Remove HTML tags from a fragment and unescape entities. Good enough
    for search snippets — not meant to handle arbitrary/malicious HTML."""
    text = re.sub(r"<[^>]+>", "", html_fragment)
    return unescape(text).strip()


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web via DuckDuckGo's HTML results page.

    Returns a list of {"title": str, "snippet": str, "url": str} dicts.
    Returns an empty list on any failure (network error, no results,
    parsing failure) rather than raising — callers should treat an empty
    list as "no search context available" and proceed without it."""

    if not query or not query.strip():
        return []

    try:
        response = requests.post(
            SEARCH_URL,
            data={"q": query},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as e:
        print(f"[Levi] Web search request failed: {e}")
        return []

    html = response.text
    results: list[dict] = []

    # DuckDuckGo's HTML results follow a consistent structural pattern:
    # each result sits in a block with class="result__body", containing
    # a result__a (title+link) and result__snippet. Regex is fragile
    # against markup changes, but avoids adding a full HTML parser
    # dependency for what is otherwise a fairly simple extraction.
    result_blocks = re.findall(
        r'<div class="result results_links[^"]*result--url-above-snippet">'
        r'.*?<a[^>]+href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )

    if not result_blocks:
        # Fallback pattern — DuckDuckGo occasionally varies class ordering.
        result_blocks = re.findall(
            r'<a[^>]+href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>'
            r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

    for url, title_html, snippet_html in result_blocks[:max_results]:
        # DuckDuckGo's HTML endpoint wraps outbound links in a redirect —
        # unwrap it to get the real destination URL where possible.
        clean_url = url
        redirect_match = re.search(r"uddg=([^&]+)", url)
        if redirect_match:
            from urllib.parse import unquote
            clean_url = unquote(redirect_match.group(1))

        results.append({
            "title": _strip_tags(title_html),
            "snippet": _strip_tags(snippet_html),
            "url": clean_url,
        })

    return results


def format_search_results_for_prompt(results: list[dict], query: str) -> Optional[str]:
    """Format search results into a block suitable for injecting into the
    AI's prompt context. Returns None if there are no results to inject."""
    if not results:
        return None

    lines = [f'Web search results for: "{query}"\n']
    for i, r in enumerate(results, start=1):
        lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   Source: {r['url']}")

    return "\n\n".join(lines)
