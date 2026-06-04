import type { WorkspaceView } from "@/lib/contracts/workspace";
import type { StreamWorkspaceView } from "@/lib/streamWorkspace";

export type MediumStatusTone = "success" | "warning" | "neutral";

export type MediumStatusViewModel = {
  status: "recognized" | "family_only" | "mentioned_unclassified" | "unavailable";
  statusLabel: string;
  tone: MediumStatusTone;
  label: string | null;
  family: string | null;
  confidence: string | null;
  rawMention: string | null;
  summary: string;
  nextStepHint: string | null;
};

type MediumClassificationInput = {
  canonicalLabel: string | null | undefined;
  family: string | null | undefined;
  confidence: string | null | undefined;
  status: string | null | undefined;
  followupQuestion: string | null | undefined;
};

type MediumCaptureInput = {
  primaryRawText: string | null | undefined;
  rawMentions: string[] | null | undefined;
};

function normalizeText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function humanizeToken(value: string | null | undefined): string | null {
  const text = normalizeText(value);
  if (!text) {
    return null;
  }

  const labels: Record<string, string> = {
    recognized: "erkannt",
    family_only: "Familienkontext erkannt",
    mentioned_unclassified: "genannt, noch nicht eingeordnet",
    unavailable: "noch offen",
    waessrig: "wässrig",
    waessrig_salzhaltig: "wässrig, salzhaltig",
    oelhaltig: "ölhaltig",
    gasfoermig: "gasförmig",
    dampffoermig: "dampfförmig",
    loesemittelhaltig: "lösungsmittelhaltig",
    chemisch_aggressiv: "chemisch aggressiv",
    lebensmittelnah: "lebensmittelnah",
    partikelhaltig: "partikelhaltig",
    unknown: "noch nicht eingeordnet",
    high: "hoch",
    medium: "mittel",
    low: "niedrig",
    confirmed: "hoch",
  };

  return labels[text] || text.replace(/_/g, " ");
}

function pickRawMention(capture: MediumCaptureInput): string | null {
  const primary = normalizeText(capture.primaryRawText);
  if (primary) {
    return primary;
  }

  const mentions = Array.isArray(capture.rawMentions) ? capture.rawMentions : [];
  for (const mention of mentions) {
    const normalized = normalizeText(mention);
    if (normalized) {
      return normalized;
    }
  }
  return null;
}

function buildMediumStatusView(
  classification: MediumClassificationInput,
  capture: MediumCaptureInput,
): MediumStatusViewModel {
  const rawMention = pickRawMention(capture);
  const status =
    classification.status === "recognized" ||
    classification.status === "family_only" ||
    classification.status === "mentioned_unclassified"
      ? classification.status
      : "unavailable";
  const family =
    classification.family && classification.family !== "unknown"
      ? humanizeToken(classification.family)
      : null;
  const confidence =
    status === "unavailable" ? null : humanizeToken(classification.confidence || null);
  const followupQuestion = normalizeText(classification.followupQuestion);

  switch (status) {
    case "recognized":
      return {
        status,
        statusLabel: "erkannt",
        tone: "success",
        label: normalizeText(classification.canonicalLabel),
        family,
        confidence,
        rawMention,
        summary: "Das Medium wurde erkannt und für die weitere Klärung eingeordnet.",
        nextStepHint:
          followupQuestion ||
          "Als Nächstes die Einsatzbedingungen wie Temperatur, Druck oder Konzentration präzisieren.",
      };
    case "family_only":
      return {
        status,
        statusLabel: "Familienkontext erkannt",
        tone: "warning",
        label: family,
        family,
        confidence,
        rawMention,
        summary: "Ein Medienkontext wurde erkannt, die genaue Einordnung ist aber noch zu präzisieren.",
        nextStepHint:
          followupQuestion || "Als Nächstes die genaue Stoffart oder Konzentration präzisieren.",
      };
    case "mentioned_unclassified":
      return {
        status,
        statusLabel: "genannt, noch nicht eingeordnet",
        tone: "warning",
        label: rawMention,
        family,
        confidence,
        rawMention,
        summary: "Ein Medium wurde genannt, konnte aber noch nicht belastbar klassifiziert werden.",
        nextStepHint:
          followupQuestion ||
          "Als Nächstes den Stoff, die Zusammensetzung oder den Produktnamen näher einordnen.",
      };
    default:
      return {
        status: "unavailable",
        statusLabel: "noch offen",
        tone: "neutral",
        label: null,
        family: null,
        confidence: null,
        rawMention: null,
        summary: "Für die weitere Einordnung fehlt noch eine Angabe zum Medium.",
        nextStepHint: "Als Nächstes das Medium angeben.",
      };
  }
}

export function buildMediumStatusViewFromWorkspace(
  workspace: WorkspaceView,
): MediumStatusViewModel {
  return buildMediumStatusView(workspace.mediumClassification, workspace.mediumCapture);
}

export function buildMediumStatusViewFromStream(
  streamWorkspace: StreamWorkspaceView,
): MediumStatusViewModel {
  return buildMediumStatusView(
    {
      canonicalLabel: streamWorkspace.ui.medium_classification.canonical_label,
      family: streamWorkspace.ui.medium_classification.family,
      confidence: streamWorkspace.ui.medium_classification.confidence,
      status: streamWorkspace.ui.medium_classification.status,
      followupQuestion: streamWorkspace.ui.medium_classification.followup_question,
    },
    {
    primaryRawText: streamWorkspace.ui.medium_classification.primary_raw_text,
    rawMentions: streamWorkspace.ui.medium_classification.raw_mentions,
    },
  );
}
