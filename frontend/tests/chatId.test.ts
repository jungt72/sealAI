
import { describe, it, expect, vi, afterEach } from "vitest";
import { normalizeChatId, generateUuid, isUuidV4 } from "../src/lib/chatId";

describe('chatId utilities', () => {
    const uuidv4Regex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

    describe('normalizeChatId', () => {
        it('generates UUID for null/undefined/empty', () => {
            expect(normalizeChatId(null)).toMatch(uuidv4Regex);
            expect(normalizeChatId(undefined)).toMatch(uuidv4Regex);
            expect(normalizeChatId("")).toMatch(uuidv4Regex);
        });

        it('keeps valid UUIDv4', () => {
            const v4 = 'f47ac10b-58cc-4372-a567-0e02b2c3d479';
            expect(normalizeChatId(v4)).toBe(v4);
        });

        it('regenerates for legacy IDs', () => {
            const legacy = "chat-123";
            const normalized = normalizeChatId(legacy);
            expect(normalized).not.toBe(legacy);
            expect(normalized).toMatch(uuidv4Regex);
        });
    });

    describe('generateUuid', () => {
        it('generates valid UUIDs in standard env', () => {
            const id = generateUuid();
            expect(id).toMatch(uuidv4Regex);
        });

        it('uses fallback when crypto.randomUUID is missing', () => {
            // Mock global crypto
            const originalCrypto = globalThis.crypto;

            // Force fallback by hiding randomUUID
            // Note: simplistic mock for test isolation
            Object.defineProperty(globalThis, 'crypto', {
                value: {
                    ...originalCrypto,
                    randomUUID: undefined,
                    getRandomValues: (arr: Uint8Array) => originalCrypto.getRandomValues(arr)
                },
                writable: true,
                configurable: true
            });

            const id = generateUuid();
            expect(id).toMatch(uuidv4Regex);

            // Restore
            Object.defineProperty(globalThis, 'crypto', { value: originalCrypto });
        });
    });
});
