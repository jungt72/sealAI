export const isParamSyncDebug = (): boolean =>
  process.env.NEXT_PUBLIC_PARAM_SYNC_DEBUG === "1";

export const dbg = (...args: unknown[]): void => {
  if (!isParamSyncDebug()) return;
  console.debug("[param-sync]", ...args);
};
