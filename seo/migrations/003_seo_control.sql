CREATE TABLE IF NOT EXISTS seo_crawl_runs (
  run_id TEXT PRIMARY KEY,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  base_url TEXT NOT NULL,
  sitemap_url TEXT NOT NULL,
  urls_discovered INTEGER NOT NULL DEFAULT 0,
  urls_checked INTEGER NOT NULL DEFAULT 0,
  indexable_urls INTEGER NOT NULL DEFAULT 0,
  issue_urls INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS seo_url_checks (
  run_id TEXT NOT NULL,
  url TEXT NOT NULL,
  final_url TEXT,
  status_code INTEGER,
  content_type TEXT,
  indexable INTEGER NOT NULL DEFAULT 0,
  robots_meta TEXT,
  canonical_url TEXT,
  canonical_ok INTEGER NOT NULL DEFAULT 0,
  title TEXT,
  title_length INTEGER NOT NULL DEFAULT 0,
  meta_description TEXT,
  description_length INTEGER NOT NULL DEFAULT 0,
  h1_count INTEGER NOT NULL DEFAULT 0,
  jsonld_blocks INTEGER NOT NULL DEFAULT 0,
  jsonld_valid INTEGER NOT NULL DEFAULT 1,
  internal_links_count INTEGER NOT NULL DEFAULT 0,
  inbound_internal_links_count INTEGER NOT NULL DEFAULT 0,
  issue_count INTEGER NOT NULL DEFAULT 0,
  issues_json TEXT NOT NULL DEFAULT '[]',
  checked_at_utc TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'seo_indexability_crawler',
  PRIMARY KEY (run_id, url),
  FOREIGN KEY (run_id) REFERENCES seo_crawl_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_seo_url_checks_url
ON seo_url_checks (url, checked_at_utc);

CREATE INDEX IF NOT EXISTS idx_seo_url_checks_indexable
ON seo_url_checks (run_id, indexable, issue_count);

CREATE TABLE IF NOT EXISTS seo_internal_links (
  run_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  target_url TEXT NOT NULL,
  anchor_text TEXT NOT NULL DEFAULT '',
  rel TEXT NOT NULL DEFAULT '',
  link_type TEXT NOT NULL CHECK (link_type IN ('internal', 'external')),
  source TEXT NOT NULL DEFAULT 'seo_indexability_crawler',
  FOREIGN KEY (run_id) REFERENCES seo_crawl_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_seo_internal_links_target
ON seo_internal_links (run_id, target_url);

CREATE TABLE IF NOT EXISTS gsc_url_inspection_runs (
  run_id TEXT PRIMARY KEY,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  site_url TEXT NOT NULL,
  urls_requested INTEGER NOT NULL DEFAULT 0,
  urls_inspected INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS gsc_url_inspection (
  run_id TEXT NOT NULL,
  inspection_url TEXT NOT NULL,
  site_url TEXT NOT NULL,
  verdict TEXT,
  coverage_state TEXT,
  indexing_state TEXT,
  page_fetch_state TEXT,
  robots_txt_state TEXT,
  google_canonical TEXT,
  user_canonical TEXT,
  last_crawl_time TEXT,
  sitemap_json TEXT NOT NULL DEFAULT '[]',
  raw_json TEXT NOT NULL DEFAULT '{}',
  inspected_at_utc TEXT NOT NULL,
  PRIMARY KEY (run_id, inspection_url),
  FOREIGN KEY (run_id) REFERENCES gsc_url_inspection_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_gsc_url_inspection_url
ON gsc_url_inspection (site_url, inspection_url, inspected_at_utc);

CREATE TABLE IF NOT EXISTS dataforseo_serp_runs (
  run_id TEXT PRIMARY KEY,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  endpoint TEXT NOT NULL,
  planned_cost_usd REAL NOT NULL DEFAULT 0,
  actual_cost_usd REAL NOT NULL DEFAULT 0,
  location_code INTEGER NOT NULL,
  language_code TEXT NOT NULL,
  keywords_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS dataforseo_serp_results (
  run_id TEXT NOT NULL,
  keyword TEXT NOT NULL,
  location_code INTEGER NOT NULL,
  language_code TEXT NOT NULL,
  collected_at_utc TEXT NOT NULL,
  rank_group INTEGER,
  rank_absolute INTEGER,
  result_type TEXT NOT NULL,
  domain TEXT,
  url TEXT,
  title TEXT,
  description TEXT,
  breadcrumb TEXT,
  is_target_domain INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL DEFAULT 'dataforseo_serp_google_organic_live_advanced',
  FOREIGN KEY (run_id) REFERENCES dataforseo_serp_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dataforseo_serp_keyword
ON dataforseo_serp_results (keyword, location_code, language_code, rank_absolute);

CREATE INDEX IF NOT EXISTS idx_dataforseo_serp_target
ON dataforseo_serp_results (run_id, is_target_domain, rank_absolute);
