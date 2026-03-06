import test from "node:test";
import assert from "node:assert/strict";

import { extractRenderableAssistantText } from "./useSealAIStreamContract.js";

test("extractRenderableAssistantText prefers governed output over preview mirrors", () => {
  assert.equal(
    extractRenderableAssistantText({
      type: "done",
      governed_output_text: "Freigegebene Antwort",
      final_text: "Legacy Spiegel",
    }),
    "Freigegebene Antwort",
  );
});

test("extractRenderableAssistantText prefers done payload final_text", () => {
  assert.equal(
    extractRenderableAssistantText({
      type: "done",
      chat_id: "chat-1",
      final_text: "Kyrolon ist ein PTFE-Compound.",
      final_answer: "ignored",
    }),
    "Kyrolon ist ein PTFE-Compound.",
  );
});

test("extractRenderableAssistantText resolves nested state_update final_text", () => {
  assert.equal(
    extractRenderableAssistantText({
      type: "state_update",
      data: {
        final_text: "Kyrolon hat gute chemische Beständigkeit.",
      },
    }),
    "Kyrolon hat gute chemische Beständigkeit.",
  );
});

test("extractRenderableAssistantText falls back to assistant messages", () => {
  assert.equal(
    extractRenderableAssistantText({
      messages: [
        { role: "user", content: "Was kannst du mir über Kyrolon sagen?" },
        { role: "assistant", content: "Kyrolon ist ein PTFE-Compound." },
      ],
    }),
    "Kyrolon ist ein PTFE-Compound.",
  );
});
