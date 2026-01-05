export type Phase =
  | "rapport"
  | "warmup"
  | "bedarfsanalyse"
  | "berechnung"
  | "auswahl"
  | "review"
  | "exit";

export type FlowMeta = {
  phase?: Phase | string;
  confidence?: number | null;
  reviewLoops?: number;
  memoryContextLoaded?: boolean;
  memoryCommitted?: boolean;
  arbiter?: boolean;
  longTermMemoryRefs?: number;
};

export type MessageMeta = {
  final?: unknown;
  flow?: FlowMeta;
  [key: string]: unknown;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  createdAt: string;
  meta?: MessageMeta;
};
