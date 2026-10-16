"""Polite crawler: robots.txt, sitemap discovery, rate limiting, JS-shell fallbacks, URL/content dedupe."""
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from app.core.config import Settings

log = logging.getLogger(__name__)

SKIP_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".mp4", ".mp3", ".css", ".js", ".ico", ".xml.gz")
TRACKING = ("utm_", "fbclid", "gclid", "ref", "mc_", "igshid")
NOISE_RE = re.compile(r"cookie|consent|banner|navbar|menu|sidebar|footer|popup|modal", re.I)


@dataclass
class FetchResult:
    status_code: int
    text: str = ""
    content_type: str = "text/html"
    url: str = ""


@dataclass
class PageContent:
    url: str
    title: str
    description: str | None
    headings: list[str]
    text: str
    links: list[str]
    method: str  # static | embedded_json | public_api | playwright
    content_hash: str
    enroll_url: str | None = None


@dataclass
class CrawlResult:
    pages: list[PageContent] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)
    fetched: int = 0
    errors: list[str] = field(default_factory=list)


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(TRACKING)]
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", urlencode(q), ""))


def default_fetch(settings: Settings):
    session = requests.Session()
    session.headers["User-Agent"] = settings.crawl_user_agent

    def fetch(url: str) -> FetchResult:
        last = None
        for attempt in range(3):
            try:
                r = session.get(url, timeout=settings.crawl_timeout_seconds)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return FetchResult(r.status_code, r.text, r.headers.get("Content-Type", ""), r.url)
            except requests.RequestException as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise last or RuntimeError("fetch failed")

    return fetch


def render_with_playwright(url: str, user_agent: str) -> str | None:
    """Optional JS rendering. Requires `pip install playwright` + `playwright install chromium`."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("ENABLE_PLAYWRIGHT=true but playwright is not installed; skipping render fallback")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=user_agent)
            page.goto(url, wait_until="networkidle", timeout=30000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.warning("Playwright render failed for %s: %s", url, type(e).__name__)
        return None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def extract_page(html: str, base_url: str) -> dict:
    """Return title, description, headings, text, links, enroll_url. Navigation/footer/scripts are removed."""
    soup = BeautifulSoup(html, "html.parser")
    links = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True)]
    enroll = None
    for a in soup.find_all("a", href=True):
        if re.search(r"enrol|enroll|buy now|join (now|course)|get started", a.get_text(" "), re.I):
            enroll = urljoin(base_url, a["href"])
            break
    title = _clean(soup.title.get_text()) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    description = _clean(meta.get("content", "")) if meta else None
    json_blobs = [s.string or "" for s in soup.find_all("script") if s.get("type") in ("application/ld+json", "application/json") or s.get("id") == "__NEXT_DATA__"]
    scripts_text = " ".join(s.string or "" for s in soup.find_all("script"))
    for t in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe"]):
        t.decompose()
    for el in soup.find_all(True):
        if el.attrs is None:
            continue
        ident = " ".join([*(el.get("class") or []), el.get("id") or ""])
        if ident and NOISE_RE.search(ident):
            el.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    headings = [_clean(h.get_text(" ")) for h in root.find_all(["h1", "h2", "h3"])]
    pieces: list[str] = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "td", "th"]):
        t = _clean(el.get_text(" "))
        if len(t) >= 3 and (not pieces or pieces[-1] != t):
            pieces.append(t)
    text = "\n\n".join(dict.fromkeys(pieces))
    if not text:
        text = _clean(root.get_text(" "))
    return {"title": title, "description": description, "headings": [h for h in headings if h], "text": text,
            "links": links, "enroll_url": enroll, "json_blobs": json_blobs, "scripts_text": scripts_text}


def _json_strings(obj, out: list[str]) -> None:
    if isinstance(obj, str):
        s = _clean(obj)
        if len(s) >= 20 and " " in s and not s.startswith(("http", "/", "{", "<")):
            out.append(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            _json_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _json_strings(v, out)


def text_from_json(raw: str) -> str:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    out: list[str] = []
    _json_strings(data, out)
    return "\n\n".join(dict.fromkeys(out))


class Crawler:
    def __init__(self, settings: Settings, fetch=None, sleep=time.sleep, clock=time.monotonic, render=None):
        self.s = settings
        self._fetch = fetch or default_fetch(settings)
        self._sleep, self._clock = sleep, clock
        self._render = render or (lambda url: render_with_playwright(url, settings.crawl_user_agent))
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._sitemaps: dict[str, list[str]] = {}

    # ---- helpers ----------------------------------------------------
    def in_scope(self, url: str) -> bool:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        return p.scheme in ("http", "https") and any(host == d or host.endswith("." + d) for d in self.s.domains) \
            and not p.path.lower().endswith(SKIP_EXT)

    def _get(self, url: str) -> FetchResult:
        host = urlparse(url).netloc
        wait = self.s.crawl_delay_seconds - (self._clock() - self._last_hit.get(host, -1e9))
        if wait > 0:
            self._sleep(wait)
        self._last_hit[host] = self._clock()
        return self._fetch(url)

    def _robots_for(self, url: str):
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self._get(origin + "/robots.txt")
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._sitemaps[origin] = list(rp.site_maps() or [])
                elif 400 <= r.status_code < 500:
                    rp.parse([])  # no robots.txt -> everything allowed
                else:
                    rp = None  # 5xx: be conservative
            except Exception:
                rp = None
            self._robots[origin] = rp
        return self._robots[origin]

    def allowed(self, url: str) -> tuple[bool, str]:
        rp = self._robots_for(url)
        if rp is None:
            return False, "robots_unavailable"
        return (rp.can_fetch(self.s.crawl_user_agent, url), "robots_disallowed")

    def _sitemap_urls(self, origin: str, depth: int = 0) -> list[str]:
        self._robots_for(origin + "/")
        queue = self._sitemaps.get(origin, []) or [origin + "/sitemap.xml"]
        found: list[str] = []
        seen: set[str] = set()
        while queue and len(seen) < 20:
            sm = queue.pop(0)
            if sm in seen or not self.in_scope(sm):
                continue
            seen.add(sm)
            try:
                r = self._get(sm)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
                (queue if loc.lower().endswith(".xml") else found).append(loc)
        return found

    # ---- fallbacks --------------------------------------------------
    def _fallbacks(self, url: str, info: dict) -> tuple[str, str, str | None]:
        """Return (text, method, rendered_html). First fallback with enough text wins."""
        minlen = self.s.crawl_min_text_chars
        blob_text = "\n\n".join(filter(None, (text_from_json(b) for b in info["json_blobs"])))
        if len(blob_text) >= minlen:
            return blob_text, "embedded_json", None
        origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
        cands = re.findall(r"""["'](/api/[^"'\s<>\\]+)["']""", info["scripts_text"] + " ".join(info["json_blobs"]))
        for path in list(dict.fromkeys(cands))[:5]:
            api = origin + path
            ok, _ = self.allowed(api)
            if not ok or not self.in_scope(api):
                continue
            try:
                r = self._get(api)
            except Exception:
                continue
            if r.status_code == 200:
                t = text_from_json(r.text)
                if len(t) >= minlen:
                    return t, "public_api", None
        if self.s.enable_playwright:
            html = self._render(url)
            if html:
                rendered = extract_page(html, url)
                if len(rendered["text"]) >= minlen:
                    return rendered["text"], "playwright", html
        return "", "", None

    # ---- main loop --------------------------------------------------
    def crawl(self, max_pages: int | None = None) -> CrawlResult:
        res = CrawlResult()
        limit = max_pages or self.s.crawl_max_pages
        queue: list[tuple[str, int]] = []
        seen: set[str] = set()
        hashes: set[str] = set()
        for seed in self.s.seed_urls:
            origin = "{0.scheme}://{0.netloc}".format(urlparse(seed))
            queue.append((normalize_url(seed), 0))
            for u in self._sitemap_urls(origin):
                if self.in_scope(u):
                    queue.append((normalize_url(u), 1))
        while queue and res.fetched < limit:
            url, depth = queue.pop(0)
            if url in seen or not self.in_scope(url):
                continue
            seen.add(url)
            ok, reason = self.allowed(url)
            if not ok:
                res.skipped.append((url, reason))
                continue
            try:
                r = self._get(url)
            except Exception as e:
                res.errors.append(f"{url}: {type(e).__name__}")
                res.skipped.append((url, "fetch_error"))
                continue
            res.fetched += 1
            if r.status_code != 200:
                res.skipped.append((url, f"http_{r.status_code}"))
                continue
            if "html" not in (r.content_type or "html").lower():
                res.skipped.append((url, "non_html"))
                continue
            info = extract_page(r.text, url)
            text, method = info["text"], "static"
            if len(text) < self.s.crawl_min_text_chars:
                text, method, rendered = self._fallbacks(url, info)
                if not text:
                    res.skipped.append((url, "skipped_no_content"))
                    self._enqueue(queue, info["links"], depth, seen)
                    continue
                if rendered:
                    info["links"] += extract_page(rendered, url)["links"]
            h = hashlib.sha256(text.encode()).hexdigest()
            if h in hashes:
                res.skipped.append((url, "duplicate"))
                continue
            hashes.add(h)
            res.pages.append(PageContent(url, info["title"], info["description"], info["headings"], text,
                                         info["links"], method, h, info["enroll_url"]))
            self._enqueue(queue, info["links"], depth, seen)
        return res

    def _enqueue(self, queue, links, depth, seen) -> None:
        if depth >= self.s.crawl_max_depth:
            return
        for l in links:
            n = normalize_url(l)
            if n not in seen and self.in_scope(n):
                queue.append((n, depth + 1))
