import { randomUUID } from "node:crypto";

import { NextResponse } from "next/server";

import type {
  AgentConversationStrategy,
  AgentStreamRequest,
  AgentTurnContext,
} from "@/lib/contracts/agent";
import { isOutwardResponseClass } from "@/lib/contracts/agent";
import { applyBffCookieUpdates, getAccessTokenResult } from "@/lib/bff/auth-token";
import { BffError } from "@/lib/bff/http";
import { buildBackendUrl } from "@/lib/bff/backend";

function encodeSseEvent(payload: Record<string, unknown>): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(payload)}\n\n`);
}

const SYNTHETIC_STREAM_SEGMENT_CHARS = 42;
const SYNTHETIC_STREAM_SEGMENT_DELAY_MS = 14;

const IGNORED_BACKEND_EVENT_TYPES = new Set([
  "text_replacement",
  "boundary_block",
  "stream_end",
]);

type RawConversationStrategyPayload = {
  conversation_phase?: unknown;
  turn_goal?: unknown;
  primary_question?: unknown;
  supporting_reason?: unknown;
  response_mode?: unknown;
};

type RawTurnContextPayload = RawConversationStrategyPayload & {
  confirmed_facts_summary?: unknown;
  open_points_summary?: unknown;
};

function asRawConversationStrategyPayload(value: unknown): RawConversationStrategyPayload | null {
  return value && typeof value === "object"
    ? (value as RawConversationStrategyPayload)
    : null;
}

function asRawTurnContextPayload(value: unknown): RawTurnContextPayload | null {
  return value && typeof value === "object" ? (value as RawTurnContextPayload) : null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function syntheticStreamSegments(text: string): string[] {
  const clean = text || "";
  if (!clean) {
    return [];
  }
  if (clean.length <= SYNTHETIC_STREAM_SEGMENT_CHARS) {
    return [clean];
  }

  const segments: string[] = [];
  let current = "";
  for (const token of clean.match(/\S+\s*/g) ?? []) {
    if (current && current.length + token.length > SYNTHETIC_STREAM_SEGMENT_CHARS) {
      segments.push(current);
      current = token;
    } else {
      current += token;
    }
  }
  if (current) {
    segments.push(current);
  }
  return segments;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function enqueueSyntheticTextChunks(
  controller: ReadableStreamDefaultController<Uint8Array>,
  text: string,
) {
  const segments = syntheticStreamSegments(text);
  for (const segment of segments) {
    controller.enqueue(encodeSseEvent({ type: "text_chunk", text: segment }));
    if (segments.length > 1) {
      await sleep(SYNTHETIC_STREAM_SEGMENT_DELAY_MS);
    }
  }
}

function mapConversationStrategy(value: unknown): AgentConversationStrategy | null {
  const payload = asRawConversationStrategyPayload(value);
  if (!payload) {
    return null;
  }

  return {
    conversationPhase:
      typeof payload.conversation_phase === "string" ? payload.conversation_phase : "exploration",
    turnGoal: typeof payload.turn_goal === "string" ? payload.turn_goal : "continue_conversation",
    primaryQuestion:
      typeof payload.primary_question === "string" ? payload.primary_question : null,
    supportingReason:
      typeof payload.supporting_reason === "string" ? payload.supporting_reason : null,
    responseMode:
      typeof payload.response_mode === "string" ? payload.response_mode : "guided_explanation",
  };
}

function mapTurnContext(value: unknown): AgentTurnContext | null {
  const payload = asRawTurnContextPayload(value);
  if (!payload) {
    return null;
  }

  return {
    conversationPhase:
      typeof payload.conversation_phase === "string" ? payload.conversation_phase : "exploration",
    turnGoal: typeof payload.turn_goal === "string" ? payload.turn_goal : "continue_conversation",
    primaryQuestion:
      typeof payload.primary_question === "string" ? payload.primary_question : null,
    supportingReason:
      typeof payload.supporting_reason === "string" ? payload.supporting_reason : null,
    responseMode:
      typeof payload.response_mode === "string" ? payload.response_mode : "guided_explanation",
    confirmedFactsSummary: Array.isArray(payload.confirmed_facts_summary)
      ? payload.confirmed_facts_summary.filter((entry): entry is string => typeof entry === "string")
      : [],
    openPointsSummary: Array.isArray(payload.open_points_summary)
      ? payload.open_points_summary.filter((entry): entry is string => typeof entry === "string")
      : [],
  };
}

function backendSaysNoCaseCreated(runMeta: Record<string, unknown> | null): boolean {
  const fastResponder = asRecord(runMeta?.fast_responder);
  const knowledgeService = asRecord(runMeta?.knowledge_service);
  const conversation = asRecord(runMeta?.conversation);

  return Boolean(
    fastResponder?.no_case_created ||
      knowledgeService?.no_case_created ||
      conversation?.no_case_created,
  );
}

function hasRecordEntries(value: Record<string, unknown> | null): boolean {
  return Boolean(value && Object.keys(value).length > 0);
}

function shouldBindCaseFromStateUpdate({
  requestHadCaseId,
  backendNoCaseCreated,
  responseClass,
  structuredState,
  proposedCaseDelta,
  assertions,
  rfqReadinessProjection,
}: {
  requestHadCaseId: boolean;
  backendNoCaseCreated: boolean;
  responseClass: string | null;
  structuredState: Record<string, unknown> | null;
  proposedCaseDelta: Record<string, unknown> | null;
  assertions: Record<string, unknown> | null;
  rfqReadinessProjection: Record<string, unknown> | null;
}): boolean {
  if (requestHadCaseId) {
    return true;
  }
  if (backendNoCaseCreated) {
    return false;
  }
  const hasGovernedArtifacts = [
    proposedCaseDelta,
    assertions,
    rfqReadinessProjection,
  ].some(hasRecordEntries);
  if (responseClass === "conversational_answer") {
    return hasGovernedArtifacts;
  }
  if (responseClass && responseClass !== "conversational_answer") {
    return true;
  }
  return hasGovernedArtifacts || hasRecordEntries(structuredState);
}

function rawErrorText(value: unknown): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message;
  if (typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    return rawErrorText(record.message || record.detail || record.code);
  }
  return String(value);
}

function parseNestedJsonError(value: string): string {
  const trimmed = value.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
    return trimmed;
  }
  try {
    return rawErrorText(JSON.parse(trimmed)) || trimmed;
  } catch {
    return trimmed;
  }
}

function userVisibleAgentStreamError(status: number, details: unknown): string {
  const parsed = parseNestedJsonError(rawErrorText(details));
  const lowered = parsed.toLowerCase();
  if (
    status === 401 ||
    status === 403 ||
    lowered.includes("token_expired") ||
    lowered.includes("refresh token") ||
    lowered.includes("unauthorized")
  ) {
    return "Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.";
  }
  if (lowered.includes("method not allowed")) {
    return "Die Anfrage konnte nicht gesendet werden. Bitte lade die Seite neu und versuche es erneut.";
  }
  if (lowered.includes("agent stream failed") || lowered.includes("agent_stream_failed")) {
    return "Die Antwort konnte gerade nicht geladen werden. Bitte versuche es erneut.";
  }
  if (!parsed || parsed.startsWith("{") || parsed.startsWith("[")) {
    return "Die Antwort konnte gerade nicht geladen werden. Bitte versuche es erneut.";
  }
  return parsed;
}

export async function POST(request: Request) {
  try {
    const authResult = await getAccessTokenResult(request);
    const token = authResult.accessToken;
    const body = (await request.json()) as AgentStreamRequest;
    const requestHadCaseId = Boolean(body.caseId);
    const caseId = body.caseId || randomUUID();

    const backendResponse = await fetch(buildBackendUrl("/api/agent/chat/stream"), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Request-Id": randomUUID(),
      },
      body: JSON.stringify({
        message: body.message,
        session_id: caseId,
      }),
      cache: "no-store",
    });

    if (!backendResponse.ok || !backendResponse.body) {
      const details = await backendResponse.text();
      const message = userVisibleAgentStreamError(backendResponse.status || 500, details);
      const response = NextResponse.json(
        {
          error: {
            code: "agent_stream_failed",
            message,
          },
        },
        { status: backendResponse.status || 500 },
      );
      applyBffCookieUpdates(response, authResult.cookieUpdates);
      return response;
    }

    const reader = backendResponse.body.getReader();
    let emittedCaseBinding = false;
    let hasVisibleTextChunk = false;
    let buffer = "";

    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const pushCaseBinding = () => {
          if (emittedCaseBinding) {
            return;
          }
          emittedCaseBinding = true;
          controller.enqueue(encodeSseEvent({ type: "case_bound", caseId }));
        };

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }

            buffer += new TextDecoder().decode(value, { stream: true });
            const frames = buffer.split("\n\n");
            buffer = frames.pop() || "";

            for (const frame of frames) {
              const line = frame
                .split("\n")
                .find((candidate) => candidate.startsWith("data: "));

              if (!line) {
                continue;
              }

              const rawData = line.slice(6);
              if (rawData === "[DONE]") {
                controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
                continue;
              }

              let payload: Record<string, unknown>;
              try {
                payload = JSON.parse(rawData) as Record<string, unknown>;
              } catch {
                continue;
              }

              const eventType = String(payload.type || "message");
              if (IGNORED_BACKEND_EVENT_TYPES.has(eventType)) {
                continue;
              }

              if (eventType === "text_chunk") {
                const text = typeof payload.text === "string" ? payload.text : "";
                if (text) {
                  hasVisibleTextChunk = true;
                  controller.enqueue(
                    encodeSseEvent({
                      type: "text_chunk",
                      text,
                    }),
                  );
                }
                continue;
              }

              if (eventType === "text_reset") {
                hasVisibleTextChunk = false;
                controller.enqueue(encodeSseEvent({ type: "text_reset" }));
                continue;
              }

              if (eventType === "state_update") {
                const reply = typeof payload.reply === "string" ? payload.reply : "";
                const answerMarkdown =
                  typeof payload.answer_markdown === "string" ? payload.answer_markdown : null;
                const responseClass = isOutwardResponseClass(payload.response_class)
                  ? payload.response_class
                  : null;
                const runMeta = asRecord(payload.run_meta);
                const noCaseCreated = backendSaysNoCaseCreated(runMeta);
                const structuredState = asRecord(payload.structured_state);
                const proposedCaseDelta = asRecord(payload.proposed_case_delta);
                const ui = asRecord(payload.ui);
                const assertions = asRecord(payload.assertions);
                const rfqReadinessProjection = asRecord(payload.rfq_readiness_projection);
                const shouldBindCase = shouldBindCaseFromStateUpdate({
                  requestHadCaseId,
                  backendNoCaseCreated: noCaseCreated,
                  responseClass,
                  structuredState,
                  proposedCaseDelta,
                  assertions,
                  rfqReadinessProjection,
                });
                const noCaseCreatedForClient =
                  !shouldBindCase && !requestHadCaseId ? true : noCaseCreated;
                if (shouldBindCase) {
                  pushCaseBinding();
                }
                const visibleText = (answerMarkdown || reply).trim();
                if (!hasVisibleTextChunk && visibleText) {
                  await enqueueSyntheticTextChunks(controller, visibleText);
                  hasVisibleTextChunk = true;
                }
                controller.enqueue(
                  encodeSseEvent({
                    type: "state_update",
                    ...(shouldBindCase ? { caseId } : {}),
                    noCaseCreated: noCaseCreatedForClient,
                    reply,
                    ...(answerMarkdown !== null ? { answer_markdown: answerMarkdown } : {}),
                    responseClass,
                    structuredState,
                    conversationStrategy: mapConversationStrategy(payload.conversation_strategy),
                    turnContext: mapTurnContext(payload.turn_context),
                    proposedCaseDelta,
                    rfq_readiness_projection: rfqReadinessProjection,
                    ui,
                    assertions,
                    runMeta,
                  }),
                );
                continue;
              }

              if (eventType === "error") {
                const message = userVisibleAgentStreamError(
                  500,
                  typeof payload.message === "string"
                    ? payload.message
                    : "Agent stream failed.",
                );
                controller.enqueue(
                  encodeSseEvent({
                    type: "error",
                    code: "agent_stream_failed",
                    message,
                  }),
                );
              }
            }
          }

          if (buffer.trim()) {
            const line = buffer
              .split("\n")
              .find((candidate) => candidate.startsWith("data: "));
            if (line) {
              const rawData = line.slice(6);
              if (rawData === "[DONE]") {
                controller.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
              }
            }
          }
        } catch (error) {
          const message = userVisibleAgentStreamError(500, error);
          controller.enqueue(
            encodeSseEvent({
              type: "error",
              code: "agent_stream_failed",
              message,
            }),
          );
        } finally {
          controller.close();
          reader.releaseLock();
        }
      },
    });

    const response = new NextResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        Connection: "keep-alive",
      },
    });
    applyBffCookieUpdates(response, authResult.cookieUpdates);
    return response;
  } catch (error) {
    if (error instanceof BffError) {
      const message = userVisibleAgentStreamError(error.status, error.message);
      return NextResponse.json(
        { error: { code: "auth_error", message } },
        { status: error.status },
      );
    }

    console.error("[api/bff/agent/chat/stream] failed", error);

    return NextResponse.json(
      { error: { code: "agent_stream_failed", message: "Agent stream could not be started." } },
      { status: 500 },
    );
  }
}
