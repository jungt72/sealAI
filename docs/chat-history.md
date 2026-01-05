# Chat-History & Conversation-Architektur

## Überblick

- Jeder Keycloak-User kann mehrere Konversationen führen, identifiziert über eine `conversationId`.
- LangGraph bzw. LangChain halten den State in Redis, der immer mit einer Kombi aus `user_id` (Keycloak `sub`) und `conversationId` verknüpft ist.
- Die Frontend-Route `/chat/[conversationId]` lädt beim Initialisieren die Historie und setzt den Stream auf diese ID.
- Jeder API-Aufruf verifiziert den Token via Keycloak (über `CurrentUser`), `user_id` wird ausschließlich aus dem JWT gelesen.

## Datenmodell

- Sorted Set `chat:conversations:{user_id}`: Mitglieder sind `conversationId`s, Score ist `updated_at` (UTC). Eingebettete TTLs der Hashes sorgen dafür, dass alte Einträge mit `ZREMRANGEBYSCORE` im `list_conversations`-Call bereinigt werden.
- Hash `chat:conversation:{user_id}:{conversationId}`: Felder `id`, `user_id`, `title`, `updated_at`. TTL (standardmäßig 30 Tage, konfigurierbar via `CHAT_HISTORY_TTL_DAYS`) schützt vor zu alten Metadaten.
- Der Hash enthält zusätzlich `is_title_user_defined`, das verhindert, dass automatische Vorschläge manuell gesetzte Titel überschreiben.
- Der LangGraph `thread_id` (bzw. LangChain `RedisChatMessageHistory`-Session) wird als Kombination `f"{user_id}:{conversationId}"` gebildet, damit Nachrichten und Checkpoints pro User + Konversation isoliert bleiben.

## Limits & Aufräumen

- `CHAT_HISTORY_TTL_DAYS` setzt die Lebensdauer der Konversations-Hashes – sobald der TTL abläuft, fällt die Metadatenstruktur aus Redis und wird beim nächsten `list_conversations` aus dem Sorted Set entfernt.
- Optional kann `CHAT_MAX_CONVERSATIONS_PER_USER` gesetzt werden. Ist die Grenze erreicht, löschen wir die ältesten Metadatensätze (inkl. `is_title_user_defined`-Flag), damit nur die aktuellsten Gespräche pro User sichtbar bleiben.
- Limitierte Aufräumaktionen nutzen denselben Keycloak-`sub`-Scope, damit keine Chats eines anderen Users betroffen werden.

## Titelgenerierung

- Beim ersten Request einer neuen Konversation wird der erste User-Prompt als Titelvorschlag herangezogen. Aus dem Text werden Begrüßungen entfernt, Zeilenumbrüche zu Leerzeichen vereinheitlicht und das Resultat auf ~80 Zeichen gekürzt, ohne mitten im Wort zu enden.
- Sobald der Benutzer den Titel via `PATCH /api/v1/chat/conversations/{conversationId}` ändert, setzt der Backend-Service `is_title_user_defined = "1"` und verhindert weitere automatische Updates.
- Die Logik nutzt Keycloak-`sub` + Konversations-ID, um natürliche Titelvorschläge strikt nur für den aktuellen User zu speichern.

## Backend-Endpunkte

- `GET /api/v1/chat/conversations` – liefert für den authentifizierten User die sortierte Liste seiner Konversationen (Titel + `updated_at`). Keycloak `sub` wird als `user_id` verwendet.
- `PATCH /api/v1/chat/conversations/{conversationId}` – aktualisiert den Titel (z. B. erstes Benutzerprompt oder manuelles Rename). Nur der Owner kann schreiben.
- `DELETE /api/v1/chat/conversations/{conversationId}` – entfernt Hash + Sorted-Set-Eintrag und fordert den LangGraph-Checkpointer auf, den zugehörigen Thread zu löschen.
- `GET /api/v1/chat/history/{conversationId}` – lädt die gespeicherte Nachrichtenliste aus dem LangGraph-State (Keycloak-Request, prüft Conversation-Meta).

## Frontend-Routing & UI

- Neue Route `/chat/[conversationId]` nutzt `ConversationSidebar` und `ChatScreen`.
- `ConversationSidebar` lädt die Liste über `GET /chat/conversations`, trennt „Aktuell“ vs. „Ältere“ (24 h-Schwelle) und navigiert zu neuen IDs via `crypto.randomUUID()`.
- `useChat` akzeptiert eine `conversationId`, ruft vor dem Streaming den History-Endpoint auf und nutzt die ID als `thread_id`. Legacy-Fallback auf sessionStorage bleibt bestehen.

## Security / Keycloak

- `CurrentUser`-Dependency liefert `sub`/`preferred_username`. Kein `user_id` aus dem Payload wird vertraut.
- Alle Nachrichten-, State- oder History-Endpoints bauen Keys aus dem Keycloak-`sub`, so dass keine Cross-User-Historie möglich ist.

## Erweiterungen

- Titel-Autogenerierung: z. B. erste Benutzerfrage oder intern erstellte Zusammenfassung.
- Archiv/TTL: `CHAT_HISTORY_TTL_DAYS` kann in den Settings verkürzt oder verlängert werden, `list_conversations` bereinigt gelöschte Hashes.
- Zukunft: Weitere Metadaten (z. B. Tagging, Label) lassen sich in den Conversation-Hashes ergänzen.

## Monitoring & Logging

- Es gibt gezielte INFO-Logs für das Anlegen und Löschen von Konversationsmetadaten (nur `user_id`/`conversation_id`, kein Prompt-Content).
- Limit- und TTL-Operationen schreiben Warnungen, wenn das Aufräumen fehlschlägt, damit man in Produktion schnell sieht, ob Redis-Keys nicht bereinigt werden.
- Nachrichteninhalte oder vollständige JWTs landen nicht im Logging, da nur technische IDs/Timestamps geloggt werden.
