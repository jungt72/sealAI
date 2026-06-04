CREATE TABLE IF NOT EXISTS keyword_seed (
  keyword TEXT PRIMARY KEY,
  cluster TEXT NOT NULL,
  intent TEXT NOT NULL,
  page_type TEXT NOT NULL,
  v8_positioning TEXT NOT NULL,
  rfq_relevance TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 50,
  created_at_utc TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'run0_seed'
);

CREATE TABLE IF NOT EXISTS dataforseo_runs (
  run_id TEXT PRIMARY KEY,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  endpoint TEXT NOT NULL,
  planned_cost_usd REAL NOT NULL DEFAULT 0,
  actual_cost_usd REAL NOT NULL DEFAULT 0,
  location_code INTEGER,
  language_code TEXT,
  keywords_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS keyword_metrics (
  keyword TEXT NOT NULL,
  location_code INTEGER NOT NULL,
  language_code TEXT NOT NULL,
  collected_at_utc TEXT NOT NULL,
  search_volume INTEGER,
  cpc REAL,
  competition REAL,
  competition_index INTEGER,
  low_top_of_page_bid REAL,
  high_top_of_page_bid REAL,
  monthly_searches_json TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL,
  task_id TEXT,
  run_id TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  PRIMARY KEY (keyword, location_code, language_code, source)
);

CREATE INDEX IF NOT EXISTS idx_keyword_metrics_volume
ON keyword_metrics (location_code, language_code, search_volume);

CREATE INDEX IF NOT EXISTS idx_keyword_seed_cluster
ON keyword_seed (cluster, priority);
