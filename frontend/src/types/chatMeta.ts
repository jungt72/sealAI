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

export type ChatMeta = {
  quality?: QualityMeta;
  routing?: RoutingMeta;
  ragSources?: string[];
  contributors?: ContributorMeta[];
  warmup?: WarmupMeta;
  phase?: string;
  [key: string]: unknown;
};
