/* Resolved framing for the component tree: server value (GET /api/v2/framing) when available,
 * FALLBACK_FRAMING otherwise — the default means a component outside the provider (or before the
 * fetch resolves) still renders the full framing; the banner can never go blank. */

import { createContext, useContext } from "react";

import { FALLBACK_FRAMING, type Framing } from "./framing";

export const FramingContext = createContext<Framing>(FALLBACK_FRAMING);

export function useFraming(): Framing {
  return useContext(FramingContext);
}
