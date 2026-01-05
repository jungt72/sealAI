export type ContextParameterKey = "medium" | "temperature" | "pressure" | "sealingType";

export type ContextTag = {
  key: ContextParameterKey;
  label: string;
  value: string;
  unitHint?: string;
};

export type UploadedTechnicalFile = {
  name: string;
  size: number;
  type?: string;
  url?: string;
  extractedParameters?: Partial<ContextState>;
};

export type ContextState = {
  medium: string;
  temperature: string;
  pressure: string;
  sealingType: string;
  notes?: string;
  attachments: UploadedTechnicalFile[];
};

export const DEFAULT_CONTEXT_STATE: ContextState = {
  medium: "HLP 46",
  temperature: "180°C",
  pressure: "120 bar",
  sealingType: "Radialwellendichtung",
  notes: "Axial statisch · Kontaktfläche geschliffen",
  attachments: [],
};
