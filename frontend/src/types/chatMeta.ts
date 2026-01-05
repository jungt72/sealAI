export type QualityMeta = {
  approved?: boolean;
  confidence?: number;
  critique?: string;
  improved_answer?: string;
};

export type RoutingMeta = {
  confidence?: number;
  domain?: string;
  [key: string]: unknown;
};

export type ContributorMeta = {
  agent?: string;
  confidence?: number;
  role?: string;
  [key: string]: unknown;
};

export type WarmupMeta = {
  rapport?: string;
  user_mood?: string;
  ready_for_analysis?: boolean;
  [key: string]: unknown;
};

export type RagSource = {
  document_id: string;
  sha256?: string | null;
  filename?: string | null;
  page?: number | null;
  section?: string | null;
  score?: number | null;
  source?: string | null;
};

export type ChatMeta = {
  quality?: QualityMeta;
  routing?: RoutingMeta;
  ragSources?: RagSource[] | string[];
  contributors?: ContributorMeta[];
  warmup?: WarmupMeta;
  phase?: string;
  [key: string]: unknown;
};
