import { describe, expect, it } from "vitest";
import React from "react";
import { act, create } from "react-test-renderer";
import { ParamStoreProvider, useParamStore } from "../src/lib/stores/paramStore";

type StoreRefs = {
  initChat: ReturnType<typeof useParamStore>["initChat"];
  replaceFromServer: ReturnType<typeof useParamStore>["replaceFromServer"];
  applyRemoteDeltaFromSse: ReturnType<typeof useParamStore>["applyRemoteDeltaFromSse"];
  markPending: ReturnType<typeof useParamStore>["markPending"];
};

describe("useParamStore callback stability", () => {
  it("keeps action callbacks stable across rerenders", () => {
    const snapshots: StoreRefs[] = [];
    let storeApi: ReturnType<typeof useParamStore> | null = null;

    function Probe() {
      const store = useParamStore("chat-stable");
      storeApi = store;
      snapshots.push({
        initChat: store.initChat,
        replaceFromServer: store.replaceFromServer,
        applyRemoteDeltaFromSse: store.applyRemoteDeltaFromSse,
        markPending: store.markPending,
      });
      return null;
    }

    create(React.createElement(ParamStoreProvider, null, React.createElement(Probe)));

    expect(storeApi).not.toBeNull();

    act(() => {
      storeApi!.initChat({ chatId: "chat-stable" });
    });
    act(() => {
      storeApi!.applyLocalEdit("chat-stable", { pressure_bar: 5 }, { markDirty: true });
    });

    const first = snapshots[0]!;
    const last = snapshots[snapshots.length - 1]!;
    expect(last.initChat).toBe(first.initChat);
    expect(last.replaceFromServer).toBe(first.replaceFromServer);
    expect(last.applyRemoteDeltaFromSse).toBe(first.applyRemoteDeltaFromSse);
    expect(last.markPending).toBe(first.markPending);
  });
});
