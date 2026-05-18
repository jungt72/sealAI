from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import sqlite3
from urllib import error, parse, request
import xml.etree.ElementTree as ET
from uuid import uuid4

from . import db

USER_AGENT = "SealAI-SEO-Control/1.0 (+https://sealingai.com)"


@dataclass(frozen=True)
class LinkCandidate:
    href: str
    anchor_text: str
    rel: str


@dataclass(frozen=True)
class UrlCheck:
    url: str
    final_url: str | None
    status_code: int | None
    content_type: str
    indexable: bool
    robots_meta: str
    canonical_url: str
    canonical_ok: bool
    title: str
    meta_description: str
    h1_count: int
    jsonld_blocks: int
    jsonld_valid: bool
    internal_links_count: int
    inbound_internal_links_count: int
    issues: list[str]


class SeoHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description = ""
        self.robots_meta = ""
        self.canonical_url = ""
        self.h1_count = 0
        self.links: list[LinkCandidate] = []
        self.jsonld_payloads: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._in_jsonld = False
        self._current_link: dict[str, str] | None = None
        self._jsonld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = attrs_map.get("name", "").lower()
            if name == "description":
                self.meta_description = attrs_map.get("content", "").strip()
            elif name == "robots":
                self.robots_meta = attrs_map.get("content", "").strip().lower()
        elif tag == "link" and "canonical" in attrs_map.get("rel", "").lower().split():
            self.canonical_url = attrs_map.get("href", "").strip()
        elif tag == "h1":
            self.h1_count += 1
            self._in_h1 = True
        elif tag == "a":
            href = attrs_map.get("href", "").strip()
            if href:
                self._current_link = {
                    "href": href,
                    "rel": attrs_map.get("rel", "").strip().lower(),
                    "text": "",
                }
        elif tag == "script" and attrs_map.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "a" and self._current_link:
            self.links.append(
                LinkCandidate(
                    href=self._current_link["href"],
                    anchor_text=" ".join(self._current_link["text"].split())[:240],
                    rel=self._current_link["rel"],
                )
            )
            self._current_link = None
        elif tag == "script" and self._in_jsonld:
            self.jsonld_payloads.append("".join(self._jsonld_parts).strip())
            self._jsonld_parts = []
            self._in_jsonld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._current_link is not None:
            self._current_link["text"] += data
        if self._in_jsonld:
            self._jsonld_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())


def normalize_url(url: str) -> str:
    parsed = parse.urlsplit(url)
    path = parsed.path or "/"
    normalized = parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path.rstrip("/") or "/", "", ""))
    return normalized


def is_same_site(url: str, base_url: str) -> bool:
    return parse.urlsplit(url).netloc.lower() == parse.urlsplit(base_url).netloc.lower()


def fetch_bytes(url: str, *, timeout: int = 30) -> tuple[bytes, str, str, int]:
    req = request.Request(url, headers={"user-agent": USER_AGENT})
    try:
        with request.urlopen(req, timeout=timeout) as res:
            return (
                res.read(),
                res.geturl(),
                res.headers.get("content-type", ""),
                int(getattr(res, "status", 200)),
            )
    except error.HTTPError as exc:
        return exc.read(), exc.geturl(), exc.headers.get("content-type", ""), exc.code


def sitemap_urls(sitemap_url: str, *, limit: int = 5000) -> list[str]:
    payload, _final_url, _content_type, status = fetch_bytes(sitemap_url)
    if status >= 400:
        raise RuntimeError(f"sitemap fetch failed with HTTP {status}: {sitemap_url}")
    root = ET.fromstring(payload)
    urls: list[str] = []
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if root.tag.endswith("sitemapindex"):
        for loc in root.findall(".//sm:sitemap/sm:loc", namespace):
            if loc.text and len(urls) < limit:
                urls.extend(sitemap_urls(loc.text.strip(), limit=limit - len(urls)))
    else:
        for loc in root.findall(".//sm:url/sm:loc", namespace):
            if loc.text:
                urls.append(normalize_url(loc.text.strip()))
            if len(urls) >= limit:
                break
    return list(dict.fromkeys(urls))[:limit]


def jsonld_is_valid(payloads: list[str]) -> bool:
    for payload in payloads:
        if not payload:
            return False
        try:
            json.loads(payload)
        except json.JSONDecodeError:
            return False
    return True


def check_url(url: str, *, base_url: str) -> tuple[UrlCheck, list[tuple[str, str, str]]]:
    issues: list[str] = []
    payload, final_url, content_type, status_code = fetch_bytes(url)
    final_normalized = normalize_url(final_url)
    requested_normalized = normalize_url(url)
    html = payload.decode("utf-8", errors="replace")
    is_html = "text/html" in content_type.lower()
    parser = SeoHtmlParser()
    if is_html:
        parser.feed(html)
    else:
        issues.append("non_html_response")

    canonical = normalize_url(parse.urljoin(final_normalized, parser.canonical_url)) if parser.canonical_url else ""
    canonical_ok = bool(canonical) and canonical == requested_normalized
    robots_meta = parser.robots_meta
    has_noindex = "noindex" in {item.strip() for item in robots_meta.split(",") if item.strip()}
    title = parser.title
    description = parser.meta_description
    jsonld_valid = jsonld_is_valid(parser.jsonld_payloads)
    if status_code != 200:
        issues.append("http_not_200")
    if not is_same_site(final_normalized, base_url):
        issues.append("redirected_off_domain")
    elif final_normalized != requested_normalized:
        issues.append("redirected_url")
    if has_noindex:
        issues.append("robots_noindex")
    if not canonical:
        issues.append("missing_canonical")
    elif not canonical_ok:
        issues.append("canonical_mismatch")
    if not title:
        issues.append("missing_title")
    elif len(title) > 70:
        issues.append("title_too_long")
    if not description:
        issues.append("missing_meta_description")
    elif len(description) > 170:
        issues.append("meta_description_too_long")
    if parser.h1_count == 0:
        issues.append("missing_h1")
    elif parser.h1_count > 1:
        issues.append("multiple_h1")
    if parser.jsonld_payloads and not jsonld_valid:
        issues.append("invalid_jsonld")

    internal_links: list[tuple[str, str, str]] = []
    seen_targets: set[str] = set()
    for link in parser.links:
        if link.href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        target = normalize_url(parse.urljoin(final_normalized, link.href))
        link_type = "internal" if is_same_site(target, base_url) else "external"
        if link_type == "internal":
            seen_targets.add(target)
        internal_links.append((target, link.anchor_text, link.rel))
    if len(seen_targets) < 3:
        issues.append("low_internal_link_count")

    indexable = (
        status_code == 200
        and is_html
        and not has_noindex
        and canonical_ok
        and is_same_site(final_normalized, base_url)
    )
    return (
        UrlCheck(
            url=requested_normalized,
            final_url=final_normalized,
            status_code=status_code,
            content_type=content_type,
            indexable=indexable,
            robots_meta=robots_meta,
            canonical_url=canonical,
            canonical_ok=canonical_ok,
            title=title,
            meta_description=description,
            h1_count=parser.h1_count,
            jsonld_blocks=len(parser.jsonld_payloads),
            jsonld_valid=jsonld_valid,
            internal_links_count=len(seen_targets),
            inbound_internal_links_count=0,
            issues=issues,
        ),
        internal_links,
    )


def insert_check(conn: sqlite3.Connection, run_id: str, item: UrlCheck) -> None:
    conn.execute(
        """
        INSERT INTO seo_url_checks (
          run_id, url, final_url, status_code, content_type, indexable, robots_meta,
          canonical_url, canonical_ok, title, title_length, meta_description,
          description_length, h1_count, jsonld_blocks, jsonld_valid,
          internal_links_count, inbound_internal_links_count, issue_count,
          issues_json, checked_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            item.url,
            item.final_url,
            item.status_code,
            item.content_type,
            1 if item.indexable else 0,
            item.robots_meta,
            item.canonical_url,
            1 if item.canonical_ok else 0,
            item.title,
            len(item.title),
            item.meta_description,
            len(item.meta_description),
            item.h1_count,
            item.jsonld_blocks,
            1 if item.jsonld_valid else 0,
            item.internal_links_count,
            item.inbound_internal_links_count,
            len(item.issues),
            json.dumps(item.issues, ensure_ascii=False, sort_keys=True),
            db.utc_now(),
        ),
    )


def insert_links(conn: sqlite3.Connection, run_id: str, source_url: str, links: list[tuple[str, str, str]], *, base_url: str) -> None:
    for target, anchor_text, rel in links:
        conn.execute(
            """
            INSERT INTO seo_internal_links (
              run_id, source_url, target_url, anchor_text, rel, link_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_url,
                target,
                anchor_text,
                rel,
                "internal" if is_same_site(target, base_url) else "external",
            ),
        )


def update_inbound_counts(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute(
        """
        UPDATE seo_url_checks
        SET inbound_internal_links_count = (
          SELECT COUNT(*)
          FROM seo_internal_links l
          WHERE l.run_id = seo_url_checks.run_id
            AND l.target_url = seo_url_checks.url
            AND l.link_type = 'internal'
            AND l.source_url != seo_url_checks.url
        )
        WHERE run_id = ?
        """,
        (run_id,),
    )


def crawl(conn: sqlite3.Connection, *, base_url: str, sitemap_url: str, limit: int = 500) -> dict:
    run_id = str(uuid4())
    started = db.utc_now()
    conn.execute(
        """
        INSERT INTO seo_crawl_runs (
          run_id, started_at_utc, status, base_url, sitemap_url
        ) VALUES (?, ?, 'running', ?, ?)
        """,
        (run_id, started, base_url, sitemap_url),
    )
    conn.commit()
    checked = 0
    try:
        urls = sitemap_urls(sitemap_url, limit=limit)
        for url in urls:
            item, links = check_url(url, base_url=base_url)
            insert_check(conn, run_id, item)
            insert_links(conn, run_id, item.url, links, base_url=base_url)
            checked += 1
        update_inbound_counts(conn, run_id)
        row = conn.execute(
            """
            SELECT
              COUNT(*) urls_checked,
              SUM(CASE WHEN indexable = 1 THEN 1 ELSE 0 END) indexable_urls,
              SUM(CASE WHEN issue_count > 0 THEN 1 ELSE 0 END) issue_urls
            FROM seo_url_checks
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE seo_crawl_runs
            SET status = 'success', finished_at_utc = ?, urls_discovered = ?,
                urls_checked = ?, indexable_urls = ?, issue_urls = ?
            WHERE run_id = ?
            """,
            (
                db.utc_now(),
                len(urls),
                int(row["urls_checked"] or 0),
                int(row["indexable_urls"] or 0),
                int(row["issue_urls"] or 0),
                run_id,
            ),
        )
        conn.commit()
        return {
            "run_id": run_id,
            "status": "success",
            "urls_discovered": len(urls),
            "urls_checked": checked,
            "indexable_urls": int(row["indexable_urls"] or 0),
            "issue_urls": int(row["issue_urls"] or 0),
        }
    except Exception as exc:
        conn.execute(
            """
            UPDATE seo_crawl_runs
            SET status = 'failed', finished_at_utc = ?, urls_discovered = ?,
                urls_checked = ?, error_message = ?
            WHERE run_id = ?
            """,
            (db.utc_now(), 0, checked, str(exc)[:500], run_id),
        )
        conn.commit()
        raise
