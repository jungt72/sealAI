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

const SYNTHETIC_ANSWER_SEGMENT_CHARS = 42;
const SYNTHETIC_ANSWER_SEGMENT_DELAY_MS = 14;

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

function syntheticAnswerSegments(text: string): string[] {
  const clean = text || "";
  if (!clean) {
    return [];
  }
  if (clean.length <= SYNTHETIC_ANSWER_SEGMENT_CHARS) {
    return [clean];
  }

  const segments: string[] = [];
  let current = "";
  for (const token of clean.match(/\S+\s*/g) ?? []) {
    if (current && current.length + token.length > SYNTHETIC_ANSWER_SEGMENT_CHARS) {
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

async function enqueueFinalAnswerStream(
  controller: ReadableStreamDefaultController<Uint8Array>,
  text: string,
  source: "answer_markdown" | "reply",
  metadata: Record<string, unknown> = {},
) {
  const segments = syntheticAnswerSegments(text);
  if (segments.length === 0) {
    return;
  }
  controller.enqueue(encodeSseEvent({ type: "answer.stream.start", source, ...metadata }));
  for (const segment of segments) {
    controller.enqueue(encodeSseEvent({ type: "answer.token", text: segment, ...metadata }));
    if (segments.length > 1) {
      await sleep(SYNTHETIC_ANSWER_SEGMENT_DELAY_MS);
    }
  }
  controller.enqueue(encodeSseEvent({ type: "answer.done", ...metadata }));
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

function backendSaysHardNoCaseCreated(runMeta: Record<string, unknown> | null): boolean {
  const fastResponder = asRecord(runMeta?.fast_responder);
  const knowledgeService = asRecord(runMeta?.knowledge_service);

  return Boolean(fastResponder?.no_case_created || knowledgeService?.no_case_created);
}

function hasRecordEntries(value: Record<string, unknown> | null): boolean {
  return Boolean(value && Object.keys(value).length > 0);
}

function parameterCountFromUi(value: Record<string, unknown> | null): number {
  const parameter = asRecord(value?.parameter);
  if (!parameter) {
    return 0;
  }
  if (typeof parameter.parameter_count === "number" && Number.isFinite(parameter.parameter_count)) {
    return parameter.parameter_count;
  }
  return Array.isArray(parameter.parameters) ? parameter.parameters.length : 0;
}

function hasWorkspaceParameterProjection({
  ui,
  structuredState,
}: {
  ui: Record<string, unknown> | null;
  structuredState: Record<string, unknown> | null;
}): boolean {
  if (parameterCountFromUi(ui) > 0) {
    return true;
  }
  const structuredView = asRecord(structuredState?.view);
  return parameterCountFromUi(structuredView) > 0;
}

function shouldBindCaseFromStateUpdate({
  requestHadCaseId,
  backendNoCaseCreated,
  backendHardNoCaseCreated,
  responseClass,
  structuredState,
  ui,
  proposedCaseDelta,
  assertions,
  rfqReadinessProjection,
}: {
  requestHadCaseId: boolean;
  backendNoCaseCreated: boolean;
  backendHardNoCaseCreated: boolean;
  responseClass: string | null;
  structuredState: Record<string, unknown> | null;
  ui: Record<string, unknown> | null;
  proposedCaseDelta: Record<string, unknown> | null;
  assertions: Record<string, unknown> | null;
  rfqReadinessProjection: Record<string, unknown> | null;
}): boolean {
  if (requestHadCaseId) {
    return true;
  }
  const hasGovernedArtifacts = [
    proposedCaseDelta,
    assertions,
    rfqReadinessProjection,
  ].some(hasRecordEntries);
  const hasCaseParameterProjection = hasWorkspaceParameterProjection({ ui, structuredState });
  if (backendHardNoCaseCreated) {
    return false;
  }
  if (backendNoCaseCreated && !hasGovernedArtifacts && !hasCaseParameterProjection) {
    return false;
  }
  if (responseClass === "conversational_answer") {
    return hasGovernedArtifacts || hasCaseParameterProjection;
  }
  if (responseClass && responseClass !== "conversational_answer") {
    return true;
  }
  return hasGovernedArtifacts || hasCaseParameterProjection || hasRecordEntries(structuredState);
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

function agentStreamErrorCode(status: number, details: unknown): "auth_expired" | "network_error" | "agent_stream_failed" {
  const parsed = parseNestedJsonError(rawErrorText(details)).toLowerCase();
  if (
    status === 401 ||
    status === 403 ||
    parsed.includes("token_expired") ||
    parsed.includes("refresh token") ||
    parsed.includes("unauthorized")
  ) {
    return "auth_expired";
  }
  if (
    parsed.includes("network") ||
    parsed.includes("aborted") ||
    parsed.includes("terminated") ||
    parsed.includes("connection")
  ) {
    return "network_error";
  }
  return "agent_stream_failed";
}

function streamEventMetadata(
  payload: Record<string, unknown>,
  fallbackTurnId?: string,
): Record<string, unknown> {
  const metadata: Record<string, unknown> = fallbackTurnId ? { turn_id: fallbackTurnId } : {};
  for (const key of ["event_id", "eventId", "turn_id", "turnId", "sequence", "event_type", "is_final", "error_code"]) {
    if (payload[key] !== undefined && payload[key] !== null) {
      metadata[key] = payload[key];
    }
  }
  return metadata;
}

function isBackendAuthExpiry(status: number, details: unknown): boolean {
  const parsed = parseNestedJsonError(rawErrorText(details)).toLowerCase();
  return (
    status === 401 &&
    (parsed.includes("token_expired") ||
      parsed.includes("token expired") ||
      parsed.includes("expired access token") ||
      parsed.includes("unauthorized"))
  );
}

function resolveTurnId(body: AgentStreamRequest & { turn_id?: unknown; turnId?: unknown }): string {
  const candidate =
    typeof body.turnId === "string" && body.turnId.trim()
      ? body.turnId.trim()
      : typeof body.turn_id === "string" && body.turn_id.trim()
        ? body.turn_id.trim()
        : null;
  return candidate || randomUUID();
}

function buildBackendStreamRequest(
  body: AgentStreamRequest,
  sessionId: string,
  turnId: string,
  token: string,
): RequestInit {
  return {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-Request-Id": randomUUID(),
    },
    body: JSON.stringify({
      message: body.message,
      session_id: sessionId,
      turn_id: turnId,
    }),
    cache: "no-store",
  };
}

export async function POST(request: Request) {
  try {
    let authResult = await getAccessTokenResult(request);
    const body = (await request.json()) as AgentStreamRequest;
    const requestHadCaseId = Boolean(body.caseId);
    const sessionId = body.caseId || body.conversationId || randomUUID();
    const caseId = body.caseId || sessionId;
    const turnId = resolveTurnId(body);

    const backendUrl = buildBackendUrl("/api/agent/chat/stream");
    let backendResponse = await fetch(
      backendUrl,
      buildBackendStreamRequest(body, sessionId, turnId, authResult.accessToken),
    );

    if (!backendResponse.ok || !backendResponse.body) {
      const details = await backendResponse.text();
      if (isBackendAuthExpiry(backendResponse.status || 500, details)) {
        const refreshedAuthResult = await getAccessTokenResult(request, { forceRefresh: true });
        const retryResponse = await fetch(
          backendUrl,
          buildBackendStreamRequest(body, sessionId, turnId, refreshedAuthResult.accessToken),
        );
        authResult = {
          accessToken: refreshedAuthResult.accessToken,
          cookieUpdates: [...authResult.cookieUpdates, ...refreshedAuthResult.cookieUpdates],
        };
        backendResponse = retryResponse;
        if (backendResponse.ok && backendResponse.body) {
          // Continue with the successful retried stream below.
        } else {
          const retryDetails = await backendResponse.text();
          const message = userVisibleAgentStreamError(backendResponse.status || 500, retryDetails);
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
      } else {
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
    }

    const reader = backendResponse.body.getReader();
    let emittedCaseBinding = false;
    let finalAnswerStreamed = false;
    let buffer = "";

    const stream = new ReadableStream<Uint8Array>({
      async start(controller) {
        const pushCaseBinding = () => {
          if (emittedCaseBinding) {
            return;
          }
          emittedCaseBinding = true;
          controller.enqueue(encodeSseEvent({ type: "case_bound", caseId, turn_id: turnId }));
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
                continue;
              }

              if (eventType === "text_reset") {
                continue;
              }

              if (eventType === "progress") {
                controller.enqueue(
                  encodeSseEvent({
                    type: "progress",
                    ...streamEventMetadata(payload, turnId),
                    data: payload.data,
                  }),
                );
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
                const hardNoCaseCreated = backendSaysHardNoCaseCreated(runMeta);
                const structuredState = asRecord(payload.structured_state);
                const proposedCaseDelta = asRecord(payload.proposed_case_delta);
                const ui = asRecord(payload.ui);
                const assertions = asRecord(payload.assertions);
                const rfqReadinessProjection = asRecord(payload.rfq_readiness_projection);
                const turnEnvelope = asRecord(payload.turn_envelope);
                const turnBoundaryDecision = asRecord(payload.turn_boundary_decision);
                const finalAnswerContext = asRecord(payload.final_answer_context);
                const nonTechnicalAnswerContext = asRecord(payload.nontechnical_answer_context);
                const finalGuardResult = asRecord(payload.final_guard_result);
                const v92Dashboard = asRecord(payload.v92_dashboard);
                const shouldBindCase = shouldBindCaseFromStateUpdate({
                  requestHadCaseId,
                  backendNoCaseCreated: noCaseCreated,
                  backendHardNoCaseCreated: hardNoCaseCreated,
                  responseClass,
                  structuredState,
                  ui,
                  proposedCaseDelta,
                  assertions,
                  rfqReadinessProjection,
                });
                const noCaseCreatedForClient = shouldBindCase
                  ? false
                  : !requestHadCaseId
                    ? true
                    : noCaseCreated;
                if (shouldBindCase) {
                  pushCaseBinding();
                }
                const visibleText = (answerMarkdown || reply).trim();
                if (!finalAnswerStreamed && visibleText) {
                  await enqueueFinalAnswerStream(
                    controller,
                    visibleText,
                    answerMarkdown && answerMarkdown.trim() ? "answer_markdown" : "reply",
                    streamEventMetadata(payload, turnId),
                  );
                  finalAnswerStreamed = true;
                }
                controller.enqueue(
                  encodeSseEvent({
                    type: "state_update",
                    ...streamEventMetadata(payload, turnId),
                    ...(shouldBindCase ? { caseId } : {}),
                    noCaseCreated: noCaseCreatedForClient,
                    reply,
                    ...(answerMarkdown !== null ? { answer_markdown: answerMarkdown } : {}),
                    responseClass,
                    structuredState,
                    conversationStrategy: mapConversationStrategy(payload.conversation_strategy),
                    turnContext: mapTurnContext(payload.turn_context),
                    turnEnvelope,
                    turnBoundaryDecision,
                    finalAnswerContext,
                    nonTechnicalAnswerContext,
                    finalGuardResult,
                    v92Dashboard,
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
                    ...streamEventMetadata(payload, turnId),
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
          const errorCode = agentStreamErrorCode(500, error);
          const message =
            errorCode === "network_error"
              ? "Die Verbindung zur Antwort wurde unterbrochen. Bitte versuche es erneut."
              : userVisibleAgentStreamError(500, error);
          controller.enqueue(
            encodeSseEvent({
              type: "interrupted",
              code: errorCode,
              error_code: errorCode,
              turn_id: turnId,
              message,
              is_final: false,
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
