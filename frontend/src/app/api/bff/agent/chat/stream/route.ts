import { randomUUID } from "node:crypto";

import { NextResponse } from "next/server";

import type {
  AgentConversationStrategy,
  AgentStreamRequest,
  AgentTurnContext,
} from "@/lib/contracts/agent";
import { isOutwardResponseClass } from "@/lib/contracts/agent";
import { getAccessToken } from "@/lib/bff/auth-token";
import { BffError } from "@/lib/bff/http";
import { buildBackendUrl } from "@/lib/bff/backend";

function encodeSseEvent(payload: Record<string, unknown>): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(payload)}\n\n`);
}

const IGNORED_BACKEND_EVENT_TYPES = new Set([
  "text_chunk",
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

export async function POST(request: Request) {
  try {
    const token = await getAccessToken(request);
    const body = (await request.json()) as AgentStreamRequest;
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
      return NextResponse.json(
        {
          error: {
            code: "agent_stream_failed",
            message: details || `agent_stream_failed:${backendResponse.status}`,
          },
        },
        { status: backendResponse.status || 500 },
      );
    }

    const reader = backendResponse.body.getReader();
    let emittedCaseBinding = false;
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
          pushCaseBinding();

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

              if (eventType === "state_update") {
                const reply = typeof payload.reply === "string" ? payload.reply : "";
                const responseClass = isOutwardResponseClass(payload.response_class)
                  ? payload.response_class
                  : null;
                controller.enqueue(
                  encodeSseEvent({
                    type: "state_update",
                    caseId,
                    reply,
                    responseClass,
                    structuredState:
                      payload.structured_state && typeof payload.structured_state === "object"
                        ? payload.structured_state
                        : null,
                    conversationStrategy: mapConversationStrategy(payload.conversation_strategy),
                    turnContext: mapTurnContext(payload.turn_context),
                    ui: payload.ui && typeof payload.ui === "object" ? payload.ui : null,
                    assertions:
                      payload.assertions && typeof payload.assertions === "object"
                        ? payload.assertions
                        : null,
                  }),
                );
                continue;
              }

              if (eventType === "error") {
                controller.enqueue(
                  encodeSseEvent({
                    type: "error",
                    code: "agent_stream_failed",
                    message:
                      typeof payload.message === "string"
                        ? payload.message
                        : "Agent stream failed.",
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
          controller.enqueue(
            encodeSseEvent({
              type: "error",
              code: "agent_stream_failed",
              message: error instanceof Error ? error.message : "Agent stream failed.",
            }),
          );
        } finally {
          controller.close();
          reader.releaseLock();
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    if (error instanceof BffError) {
      return NextResponse.json(
        { error: { code: "auth_error", message: error.message } },
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
