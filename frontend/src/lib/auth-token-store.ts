import { createClient, type RedisClientType } from "redis";

export type StoredAuthTokens = {
  accessToken?: string | null;
  refreshToken?: string | null;
  idToken?: string | null;
  expires_at?: number | null;
  refreshTokenExpires?: number | null;
};

const TOKEN_KEY_PREFIX = "nextauth:tokens:";
let clientPromise: Promise<RedisClientType | null> | null = null;

const tokenKey = (jti: string) => `${TOKEN_KEY_PREFIX}${jti}`;

const getRedisClient = async (): Promise<RedisClientType | null> => {
  const url = process.env.REDIS_URL;
  if (!url) return null;
  if (!clientPromise) {
    const client = createClient({ url });
    client.on("error", (err) => {
      const message = err instanceof Error ? err.message : String(err);
      console.warn("[auth] redis error", message);
    });
    clientPromise = client
      .connect()
      .then(() => client)
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        console.warn("[auth] redis connect failed", message);
        clientPromise = null;
        return null;
      });
  }
  return clientPromise;
};

export const putTokens = async (
  jti: string,
  tokens: StoredAuthTokens,
  ttlSeconds: number,
): Promise<void> => {
  const client = await getRedisClient();
  if (!client) return;
  await client.set(tokenKey(jti), JSON.stringify(tokens), { EX: ttlSeconds });
};

export const getTokens = async (jti: string): Promise<StoredAuthTokens | null> => {
  const client = await getRedisClient();
  if (!client) return null;
  const raw = await client.get(tokenKey(jti));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredAuthTokens;
  } catch {
    return null;
  }
};

export const updateTokens = async (
  jti: string,
  partial: Partial<StoredAuthTokens>,
  ttlSeconds: number,
): Promise<void> => {
  const current = await getTokens(jti);
  await putTokens(jti, { ...(current ?? {}), ...partial }, ttlSeconds);
};

export const deleteTokens = async (jti: string): Promise<void> => {
  const client = await getRedisClient();
  if (!client) return;
  await client.del(tokenKey(jti));
};
