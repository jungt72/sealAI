"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Check, ChevronRight, Loader2, Paperclip, SendHorizontal, UserRound, X } from "lucide-react";

import ChatComposer from "@/components/dashboard/ChatComposer";
import MarkdownRenderer from "@/components/markdown/MarkdownRenderer";
import { useAgentStream } from "@/hooks/useAgentStream";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { decideCaseDelta } from "@/lib/bff/caseDelta";
import { uploadRagDocument } from "@/lib/ragApi";
import type { ProposedCaseDeltaField } from "@/lib/contracts/agent";

interface ChatPaneProps {
  caseId?: string;
  onCaseBound?: (caseId: string) => void;
  onTurnComplete?: (caseId: string) => void;
  parameterConfirmation?: string | null;
}

function MessageBubble({
  role,
  content,
  isStreaming = false,
}: {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}) {
  const isUser = role === "user";

  return (
    <div className={cn("flex w-full gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#0B5BD3] text-white shadow-[0_8px_20px_rgba(11,91,211,0.16)]">
          <Bot size={16} />
        </div>
      )}
      <div
        className={cn(
          "max-w-[min(720px,84%)] rounded-[18px] border px-4 py-3 text-[14px] leading-relaxed shadow-sm",
          isUser
            ? "border-[#CFE0FF] bg-[#EEF5FF] text-[#1F3B63]"
            : "border-[#E7ECF3] bg-white text-slate-900",
          isStreaming && "border-[#BFD4FF] shadow-[#0B5BD3]/10",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <MarkdownRenderer variant="chat">{content}</MarkdownRenderer>
        )}
      </div>
      {isUser && (
        <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full border border-[#E7ECF3] bg-white text-slate-600">
          <UserRound size={16} />
        </div>
      )}
    </div>
  );
}

function formatDeltaValue(field: ProposedCaseDeltaField): string {
  const value =
    typeof field.proposed_value === "string"
      ? field.proposed_value
      : JSON.stringify(field.proposed_value);
  return [value, field.unit].filter(Boolean).join(" ");
}

const CHAT_WORKING_STATE_AUTO_ACCEPT_FIELDS = new Set([
  "medium",
  "medium_name",
  "temperature_c",
  "temperature_min",
  "temperature_max",
  "pressure_bar",
  "pressure_nominal",
  "pressure_peak",
  "speed_rpm",
  "shaft_diameter_mm",
  "shaft_diameter",
  "housing_bore",
  "installation_width",
  "geometry",
  "geometry_context",
  "sealing_type",
  "motion_type",
  "seal_location",
  "asset_type",
  "pressure_direction",
  "installation",
  "industry",
]);

function isSuppressedBogusDeltaField(field: ProposedCaseDeltaField): boolean {
  if (field.field_name !== "material") {
    return false;
  }
  const value = String(field.proposed_value ?? "").trim().toLowerCase();
  return /^(flachdichtung|flat[_\s-]?gasket|gasket|rwdr|wellendichtring|gleitringdichtung|mechanical[_\s-]?seal|o[_\s-]?ring|hydraulikdichtung)$/.test(value);
}

function isAutoAcceptableWorkingStateField(field: ProposedCaseDeltaField): boolean {
  const status = field.status || "proposed";
  return (
    status === "proposed" &&
    CHAT_WORKING_STATE_AUTO_ACCEPT_FIELDS.has(field.field_name) &&
    field.provenance !== "documented" &&
    field.provenance !== "web_hint"
  );
}

function ProposedDeltaPanel({
  caseId,
  fields,
  onSettled,
}: {
  caseId: string | undefined;
  fields: ProposedCaseDeltaField[];
  onSettled: () => void;
}) {
  const [pendingAction, setPendingAction] = useState<"accept" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (action: "accept" | "reject") => {
    if (!caseId || pendingAction) {
      return;
    }
    setPendingAction(action);
    setError(null);
    try {
      await decideCaseDelta(
        caseId,
        action,
        fields.map((field) => field.field_name),
      );
      onSettled();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aenderung konnte nicht verarbeitet werden.");
    } finally {
      setPendingAction(null);
    }
  };

  if (!caseId || fields.length === 0) {
    return null;
  }

  return (
    <div className="ml-12 max-w-[min(720px,84%)] rounded-[12px] border border-[#CFE0FF] bg-[#F8FBFF] p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#315B8D]">
            Vorgeschlagene Case-Aenderung
          </div>
          <div className="mt-2 grid gap-1.5">
            {fields.map((field) => (
              <div key={field.field_name} className="flex flex-wrap items-center gap-2 text-[12px] text-slate-700">
                <span className="font-semibold text-slate-900">{field.field_name}</span>
                <span className="rounded-md border border-[#DCE8FA] bg-white px-2 py-0.5 font-medium">
                  {formatDeltaValue(field)}
                </span>
                {field.confidence && <span className="text-slate-500">{field.confidence}</span>}
              </div>
            ))}
          </div>
          {error && <div className="mt-2 text-[12px] font-medium text-rose-700">{error}</div>}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => void decide("accept")}
            disabled={Boolean(pendingAction)}
            aria-label="Vorgeschlagene Aenderung uebernehmen"
            className="grid h-8 w-8 place-items-center rounded-md border border-emerald-200 bg-white text-emerald-700 transition-colors hover:bg-emerald-50 disabled:cursor-wait disabled:opacity-60"
          >
            {pendingAction === "accept" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
          </button>
          <button
            type="button"
            onClick={() => void decide("reject")}
            disabled={Boolean(pendingAction)}
            aria-label="Vorgeschlagene Aenderung ablehnen"
            className="grid h-8 w-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
          >
            {pendingAction === "reject" ? <Loader2 size={15} className="animate-spin" /> : <X size={15} />}
          </button>
        </div>
      </div>
    </div>
  );
}

const ROUTING_SUGGESTIONS = [
  "PTFE-RWDR für rotierende Welle",
  "Gleitringdichtung für Pumpe",
  "Bestehende Dichtung analysieren",
];

export default function ChatPane({ caseId, onCaseBound, onTurnComplete, parameterConfirmation }: ChatPaneProps) {
  const {
    activeCaseId,
    messages,
    streamingText,
    streamWorkspace,
    isStreaming,
    error,
    sendMessage,
    clearError,
  } = useAgentStream({ initialCaseId: caseId, onCaseBound, onTurnComplete });
  const registerWorkspaceCallbacks = useWorkspaceStore((s) => s.registerCallbacks);
  const setStreamWorkspace = useWorkspaceStore((s) => s.setStreamWorkspace);
  const setActiveResponseClass = useWorkspaceStore((s) => s.setActiveResponseClass);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const [settledDeltaKey, setSettledDeltaKey] = useState<string | null>(null);
  const [autoAcceptFailedKey, setAutoAcceptFailedKey] = useState<string | null>(null);
  const autoAcceptAttemptKeyRef = useRef<string | null>(null);
  const [documentDeltaFields, setDocumentDeltaFields] = useState<ProposedCaseDeltaField[]>([]);
  const [documentUploadStatus, setDocumentUploadStatus] = useState<string | null>(null);
  const [isUploadingDocument, setIsUploadingDocument] = useState(false);
  const currentCaseId = activeCaseId || caseId;

  useEffect(() => {
    setStreamWorkspace(streamWorkspace);
    setActiveResponseClass(streamWorkspace?.responseClass ?? null);
  }, [setActiveResponseClass, setStreamWorkspace, streamWorkspace]);

  useEffect(() => {
    registerWorkspaceCallbacks({
      refreshWorkspace: () => {
        if (currentCaseId) {
          onTurnComplete?.(currentCaseId);
        }
      },
      actionBridge: (text: string) => {
        void sendMessage(text);
      },
    });
  }, [currentCaseId, onTurnComplete, registerWorkspaceCallbacks, sendMessage]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages, streamingText, isStreaming, error, parameterConfirmation]);

  const hasConversation = messages.length > 0 || Boolean(streamingText) || Boolean(parameterConfirmation);
  const proposedDeltaFields = useMemo(() => {
    const fields = streamWorkspace?.proposedCaseDelta?.fields ?? [];
    return fields.filter((field) => (field.status === "proposed" || !field.status) && !isSuppressedBogusDeltaField(field));
  }, [streamWorkspace?.proposedCaseDelta]);
  const combinedDeltaFields = documentDeltaFields.length > 0 ? documentDeltaFields : proposedDeltaFields;
  const proposedDeltaKey = combinedDeltaFields
    .map((field) => `${field.field_name}:${String(field.proposed_value)}:${field.unit ?? ""}`)
    .join("|");
  const proposedDeltaDecisionKey = currentCaseId && proposedDeltaKey ? `${currentCaseId}:${proposedDeltaKey}` : "";
  const shouldAutoAcceptWorkingState =
    Boolean(proposedDeltaKey) &&
    documentDeltaFields.length === 0 &&
    streamWorkspace?.proposedCaseDelta?.source !== "document" &&
    combinedDeltaFields.length > 0 &&
    combinedDeltaFields.every(isAutoAcceptableWorkingStateField) &&
    settledDeltaKey !== proposedDeltaKey &&
    autoAcceptFailedKey !== proposedDeltaKey;
  const visibleDeltaFields =
    proposedDeltaKey && settledDeltaKey !== proposedDeltaKey && !shouldAutoAcceptWorkingState
      ? combinedDeltaFields
      : [];

  useEffect(() => {
    if (
      !currentCaseId ||
      !proposedDeltaKey ||
      !proposedDeltaDecisionKey ||
      !shouldAutoAcceptWorkingState ||
      autoAcceptAttemptKeyRef.current === proposedDeltaDecisionKey
    ) {
      return;
    }

    autoAcceptAttemptKeyRef.current = proposedDeltaDecisionKey;
    void decideCaseDelta(
      currentCaseId,
      "accept",
      combinedDeltaFields.map((field) => field.field_name),
    )
      .then(() => {
        setSettledDeltaKey(proposedDeltaKey);
        setAutoAcceptFailedKey(null);
        onTurnComplete?.(currentCaseId);
      })
      .catch(() => {
        setAutoAcceptFailedKey(proposedDeltaKey);
      });
  }, [
    combinedDeltaFields,
    currentCaseId,
    onTurnComplete,
    proposedDeltaKey,
    proposedDeltaDecisionKey,
    shouldAutoAcceptWorkingState,
  ]);

  const handleDocumentUpload = async (file: File) => {
    if (!currentCaseId) {
      setDocumentUploadStatus("Bitte zuerst den Fall mit einer Nachricht starten, dann kann das Dokument dem Case zugeordnet werden.");
      return;
    }
    setIsUploadingDocument(true);
    setDocumentUploadStatus(null);
    setDocumentDeltaFields([]);
    try {
      const response = await uploadRagDocument(file, { caseId: currentCaseId });
      const fields = response.document_delta?.fields ?? [];
      if (response.document_delta?.status === "proposed" && fields.length > 0) {
        setDocumentDeltaFields(fields as ProposedCaseDeltaField[]);
        setSettledDeltaKey(null);
        setDocumentUploadStatus("Dokument analysiert. Bitte die vorgeschlagenen Case-Daten pruefen.");
      } else if (response.document_delta?.status === "no_fields_detected") {
        setDocumentUploadStatus("Dokument gespeichert, aber keine Case-Felder sicher erkannt.");
      } else if (response.document_delta?.status === "error") {
        setDocumentUploadStatus("Dokument gespeichert, Delta-Vorschlag konnte aber nicht erzeugt werden.");
      } else {
        setDocumentUploadStatus("Dokument gespeichert.");
      }
    } catch (err) {
      setDocumentUploadStatus(err instanceof Error ? err.message : "Dokument konnte nicht hochgeladen werden.");
    } finally {
      setIsUploadingDocument(false);
    }
  };

  return (
    <div className="flex h-full w-full flex-col bg-transparent">
      <div className="flex h-[44px] shrink-0 items-center px-1">
        <div className="text-[15px] font-semibold text-[#111827]">Chat</div>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto">
        <div
          className={cn(
            "mx-auto flex min-h-full w-full max-w-[760px] flex-col px-1",
            hasConversation ? "py-4" : "justify-center py-8",
          )}
        >
          {!hasConversation ? (
            <div className="mx-auto flex w-full max-w-[620px] flex-col items-center text-center">
              <div className="grid h-16 w-16 place-items-center rounded-full border border-[#D7E5FF] bg-[#EAF2FF] text-[#0B57D0] shadow-[0_8px_24px_rgba(15,23,42,0.08)]">
                <Bot size={28} />
              </div>
              <h1 className="mt-5 text-[26px] font-semibold tracking-tight text-[#111827]">Hallo Thorsten,</h1>
              <p className="mt-3 max-w-[520px] text-[15px] leading-7 text-[#4B5563]">
                Beschreibe kurz deine Dichtungssituation. SeaLAI hilft dir, die wichtigen Punkte sauber zu klären.
              </p>
            </div>
          ) : (
            <>
              <div className="flex flex-1 flex-col gap-5 pb-4">
                {messages.map((message, index) => (
                  <MessageBubble
                    key={`${message.role}-${index}-${message.timestamp ?? ""}`}
                    role={message.role}
                    content={message.content}
                  />
                ))}

                {streamingText && <MessageBubble role="assistant" content={streamingText} isStreaming />}

                <ProposedDeltaPanel
                  caseId={currentCaseId}
                  fields={visibleDeltaFields}
                  onSettled={() => {
                    setSettledDeltaKey(proposedDeltaKey || null);
                    setDocumentDeltaFields([]);
                    setDocumentUploadStatus(null);
                    if (currentCaseId) {
                      onTurnComplete?.(currentCaseId);
                    }
                  }}
                />

                {parameterConfirmation && (
                  <MessageBubble role="assistant" content={parameterConfirmation} />
                )}

                {documentUploadStatus && (
                  <div className="ml-12 max-w-[min(720px,84%)] rounded-[10px] border border-[#E7ECF3] bg-white px-3 py-2 text-[12px] font-medium text-slate-600 shadow-sm">
                    {documentUploadStatus}
                  </div>
                )}

                {isStreaming && !streamingText && (
                  <div className="flex justify-start gap-3">
                    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#0B5BD3] text-white shadow-sm">
                      <Bot size={16} />
                    </div>
                    <div className="rounded-[18px] border border-[#E7ECF3] bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
                      SeaLAI bereitet die Antwort vor...
                    </div>
                  </div>
                )}

                {error && (
                  <div className="rounded-[18px] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
                    <div className="flex items-start justify-between gap-3">
                      <p>{error}</p>
                      <button
                        type="button"
                        onClick={clearError}
                        className="shrink-0 rounded-md px-2 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100"
                      >
                        Schliessen
                      </button>
                    </div>
                  </div>
                )}

                <div ref={scrollAnchorRef} />
              </div>

              <div className="mt-2 flex flex-wrap gap-2 pb-3">
                {[
                  "Medienliste pruefen",
                  "Anfragevorschau vorbereiten",
                  "Offene Punkte klaeren",
                ].map((item) => (
                  <button
                    key={item}
                    type="button"
                    className="rounded-full border border-[#CFE0FF] bg-white px-3 py-2 text-[12px] font-medium text-[#0B5BD3] transition-colors hover:bg-[#F5F9FF]"
                  >
                    {item}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {hasConversation && (
        <div className="p-1 pt-3">
          <div className="mx-auto max-w-[760px]">
            <ChatComposer
              onSend={(message) => void sendMessage(message)}
              onUpload={(file) => void handleDocumentUpload(file)}
              isLoading={isStreaming}
              isUploading={isUploadingDocument}
            />
            <div className="mt-3 flex items-center justify-between gap-3 px-1 text-[11px] text-slate-400">
              <div className="flex items-center gap-2">
                <Paperclip size={12} />
                Anfragebasis für die spätere Herstellerprüfung. Keine Auslegungsfreigabe.
              </div>
              <div className="hidden items-center gap-1 md:flex">
                Details anzeigen
                <ChevronRight size={12} />
              </div>
            </div>
          </div>
        </div>
      )}
      {!hasConversation && (
        <div className="p-1 pt-3">
          <div className="mx-auto max-w-[760px]">
            <ChatComposer
              onSend={(message) => void sendMessage(message)}
              onUpload={(file) => void handleDocumentUpload(file)}
              isLoading={isStreaming}
              isUploading={isUploadingDocument}
              autoFocus
            />
            <div className="mt-3 flex w-full flex-wrap justify-center gap-2">
              {ROUTING_SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => void sendMessage(suggestion)}
                  disabled={isStreaming}
                  className="inline-flex items-center gap-2 rounded-full border border-[#D9E5F7] bg-white px-3 py-2 text-[12px] font-medium leading-5 text-[#315B8D] shadow-sm transition-colors hover:border-[#AFC7EC] hover:bg-[#F8FBFF] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <SendHorizontal size={13} />
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
