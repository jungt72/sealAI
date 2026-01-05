export type UiAction =
  | {
      ui_action: "open_form";
      form_id: string;
      schema_ref?: string;   // z.B. "domains/rwdr/params@1.0.0"
      missing: string[];
      prefill: Record<string, unknown>;
    }
  | {
      ui_action: "calc_snapshot";
      derived: {
        calculated?: Record<string, number | string>;
        flags?: Record<string, unknown>;
        warnings?: string[];
        [k: string]: unknown;
      };
    }
  | Record<string, unknown>; // fallback

