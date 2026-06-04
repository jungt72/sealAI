CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gsc_sync_runs (
  run_id TEXT PRIMARY KEY,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  site_url TEXT NOT NULL,
  search_type TEXT NOT NULL,
  date_from TEXT NOT NULL,
  date_to TEXT NOT NULL,
  requests_made INTEGER NOT NULL DEFAULT 0,
  rows_fetched INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS gsc_daily_page (
  data_date TEXT NOT NULL,
  site_url TEXT NOT NULL,
  search_type TEXT NOT NULL DEFAULT 'web',
  country TEXT NOT NULL DEFAULT 'ALL',
  device TEXT NOT NULL DEFAULT 'ALL',
  page TEXT NOT NULL,
  clicks REAL NOT NULL DEFAULT 0,
  impressions REAL NOT NULL DEFAULT 0,
  ctr REAL NOT NULL DEFAULT 0,
  position REAL NOT NULL DEFAULT 0,
  data_state TEXT NOT NULL CHECK (data_state IN ('provisional', 'final')),
  ingested_at_utc TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'gsc_api',
  PRIMARY KEY (data_date, site_url, search_type, country, device, page)
);

CREATE TABLE IF NOT EXISTS gsc_daily_page_query (
  data_date TEXT NOT NULL,
  site_url TEXT NOT NULL,
  search_type TEXT NOT NULL DEFAULT 'web',
  country TEXT NOT NULL DEFAULT 'ALL',
  device TEXT NOT NULL DEFAULT 'ALL',
  page TEXT NOT NULL,
  query TEXT NOT NULL,
  query_sanitized TEXT NOT NULL,
  query_taint TEXT NOT NULL DEFAULT 'untrusted_user_search_query',
  clicks REAL NOT NULL DEFAULT 0,
  impressions REAL NOT NULL DEFAULT 0,
  ctr REAL NOT NULL DEFAULT 0,
  position REAL NOT NULL DEFAULT 0,
  data_state TEXT NOT NULL CHECK (data_state IN ('provisional', 'final')),
  ingested_at_utc TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'gsc_api',
  PRIMARY KEY (data_date, site_url, search_type, country, device, page, query)
);

CREATE INDEX IF NOT EXISTS idx_gsc_page_date
ON gsc_daily_page (site_url, search_type, data_date);

CREATE INDEX IF NOT EXISTS idx_gsc_page_page
ON gsc_daily_page (site_url, page, data_date);

CREATE INDEX IF NOT EXISTS idx_gsc_page_query_date
ON gsc_daily_page_query (site_url, search_type, data_date);

CREATE INDEX IF NOT EXISTS idx_gsc_page_query_query
ON gsc_daily_page_query (site_url, query, data_date);

CREATE INDEX IF NOT EXISTS idx_gsc_page_query_page
ON gsc_daily_page_query (site_url, page, data_date);
