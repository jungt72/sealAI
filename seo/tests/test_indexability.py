from pathlib import Path

from sealai_seo import indexability
from sealai_seo.db import apply_migrations, connect
from sealai_seo.indexability import crawl


def test_indexability_crawl_persists_url_checks_and_links(tmp_path, monkeypatch):
    sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://sealingai.com/</loc></url>
  <url><loc>https://sealingai.com/werkstoffe/ptfe</loc></url>
</urlset>"""
    home = b"""<!doctype html>
<html><head>
  <title>sealingAI</title>
  <meta name="description" content="Technische Dichtungsklaerung.">
  <link rel="canonical" href="https://sealingai.com/">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization"}</script>
</head><body>
  <h1>sealingAI</h1>
  <a href="/werkstoffe/ptfe">PTFE</a>
  <a href="/medien">Medien</a>
  <a href="/wissen">Wissen</a>
</body></html>"""
    ptfe = b"""<!doctype html>
<html><head>
  <title>PTFE Dichtung</title>
  <meta name="description" content="PTFE in der Dichtungstechnik.">
  <link rel="canonical" href="https://sealingai.com/werkstoffe/ptfe">
</head><body>
  <h1>PTFE</h1>
  <a href="/">Start</a>
  <a href="/werkstoffe/fkm">FKM</a>
  <a href="/anfrage/dichtung-auslegen-lassen">Fall klaeren</a>
</body></html>"""

    def fake_fetch(url, timeout=30):
        if url == "https://sealingai.com/sitemap.xml":
            return sitemap, url, "application/xml", 200
        if url == "https://sealingai.com/":
            return home, url, "text/html; charset=utf-8", 200
        if url == "https://sealingai.com/werkstoffe/ptfe":
            return ptfe, url, "text/html; charset=utf-8", 200
        raise AssertionError(url)

    monkeypatch.setattr(indexability, "fetch_bytes", fake_fetch)
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")

    result = crawl(
        conn,
        base_url="https://sealingai.com",
        sitemap_url="https://sealingai.com/sitemap.xml",
    )

    assert result["status"] == "success"
    assert result["urls_checked"] == 2
    assert result["indexable_urls"] == 2
    assert conn.execute("SELECT COUNT(*) FROM seo_internal_links").fetchone()[0] == 6
    ptfe_row = conn.execute(
        "SELECT inbound_internal_links_count FROM seo_url_checks WHERE url = ?",
        ("https://sealingai.com/werkstoffe/ptfe",),
    ).fetchone()
    assert ptfe_row["inbound_internal_links_count"] == 1


def test_indexability_flags_noindex_and_canonical_mismatch(tmp_path, monkeypatch):
    sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://sealingai.com/bad</loc></url>
</urlset>"""
    bad = b"""<!doctype html>
<html><head>
  <title>Bad</title>
  <meta name="robots" content="noindex">
  <meta name="description" content="Bad.">
  <link rel="canonical" href="https://sealingai.com/other">
</head><body><h1>Bad</h1></body></html>"""

    def fake_fetch(url, timeout=30):
        if url.endswith("sitemap.xml"):
            return sitemap, url, "application/xml", 200
        return bad, url, "text/html; charset=utf-8", 200

    monkeypatch.setattr(indexability, "fetch_bytes", fake_fetch)
    conn = connect(tmp_path / "seo.db")
    apply_migrations(conn, Path(__file__).parents[1] / "migrations")

    crawl(conn, base_url="https://sealingai.com", sitemap_url="https://sealingai.com/sitemap.xml")

    row = conn.execute("SELECT indexable, issues_json FROM seo_url_checks").fetchone()
    assert row["indexable"] == 0
    assert "robots_noindex" in row["issues_json"]
    assert "canonical_mismatch" in row["issues_json"]
