CREATE TABLE IF NOT EXISTS pagespeed_sync_runs (
  run_id TEXT PRIMARY KEY,
  started_at_utc TEXT NOT NULL,
  finished_at_utc TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  strategy TEXT NOT NULL CHECK (strategy IN ('mobile', 'desktop')),
  urls_scanned INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS pagespeed_url_metrics (
  run_id TEXT NOT NULL,
  url TEXT NOT NULL,
  strategy TEXT NOT NULL CHECK (strategy IN ('mobile', 'desktop')),
  performance_score REAL,
  lcp_ms REAL,
  inp_ms REAL,
  cls REAL,
  fcp_ms REAL,
  ttfb_ms REAL,
  source TEXT NOT NULL DEFAULT 'pagespeed_api',
  fetched_at_utc TEXT NOT NULL,
  PRIMARY KEY (run_id, url, strategy),
  FOREIGN KEY (run_id) REFERENCES pagespeed_sync_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pagespeed_metrics_url
ON pagespeed_url_metrics (url, strategy, fetched_at_utc);

CREATE INDEX IF NOT EXISTS idx_pagespeed_runs_status
ON pagespeed_sync_runs (status, started_at_utc);
