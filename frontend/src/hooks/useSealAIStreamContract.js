const normalizeAssistantText = (value) => {
  if (typeof value !== "string") return "";
  return value.trim();
};

const extractMessageContent = (value) => {
  if (typeof value === "string") return value.trim();
  if (!value || typeof value !== "object") return "";
  return normalizeAssistantText(value.content ?? value.text);
};

export function extractRenderableAssistantText(payload) {
  if (!payload || typeof payload !== "object") return "";

  const direct =
    normalizeAssistantText(payload.text) ||
    normalizeAssistantText(payload.governed_output_text) ||
    normalizeAssistantText(payload.final_text) ||
    normalizeAssistantText(payload.final_answer);
  if (direct) return direct;

  if (payload.data && typeof payload.data === "object") {
    const nestedText = extractRenderableAssistantText(payload.data);
    if (nestedText) return nestedText;
  }

  if (Array.isArray(payload.messages)) {
    for (let idx = payload.messages.length - 1; idx >= 0; idx -= 1) {
      const candidate = payload.messages[idx];
      if (!candidate || typeof candidate !== "object") continue;
      const role = String(candidate.role ?? candidate.type ?? "").toLowerCase();
      if (role && !["assistant", "ai", "aimessage"].includes(role)) continue;
      const text = extractMessageContent(candidate);
      if (text) return text;
    }
  }

  return "";
}
