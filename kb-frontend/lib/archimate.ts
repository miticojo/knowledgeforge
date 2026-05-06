// ArchiMate 3.2 ontology mirror — source of truth: kb-agent/ontology.yaml
// 22 entity types organized across 5 layers.

export const LAYERS = [
  "Strategy",
  "Business",
  "Application",
  "Technology",
  "Motivation",
] as const;

export type Layer = (typeof LAYERS)[number];

// Canvas palette — sharp, distinctive accents per layer.
export const LAYER_COLORS: Record<Layer, string> = {
  Strategy: "#a855f7", // violet
  Business: "#f59e0b", // amber
  Application: "#3b82f6", // blue
  Technology: "#10b981", // emerald
  Motivation: "#ef4444", // red
};

export const ENTITY_TYPES_BY_LAYER: Record<Layer, string[]> = {
  Strategy: ["Capability"],
  Business: [
    "BusinessActor",
    "BusinessRole",
    "BusinessProcess",
    "BusinessFunction",
    "BusinessService",
    "BusinessObject",
    "Contract",
  ],
  Application: [
    "ApplicationComponent",
    "ApplicationService",
    "ApplicationInterface",
    "DataObject",
  ],
  Technology: [
    "Node",
    "Device",
    "SystemSoftware",
    "TechnologyService",
    "CommunicationNetwork",
    "Artifact",
  ],
  Motivation: ["Stakeholder", "Goal", "Requirement", "Constraint"],
};

export const ALL_ENTITY_TYPES: string[] = LAYERS.flatMap(
  (l) => ENTITY_TYPES_BY_LAYER[l]
);

export const ENTITY_TYPE_TO_LAYER: Record<string, Layer> = LAYERS.reduce(
  (acc, layer) => {
    for (const t of ENTITY_TYPES_BY_LAYER[layer]) acc[t] = layer;
    return acc;
  },
  {} as Record<string, Layer>
);

export const CONFIDENCE_OPTIONS = [
  { value: "all", label: "All" },
  { value: "extracted", label: "EXTRACTED only" },
  { value: "extracted_inferred", label: "EXTRACTED + INFERRED" },
  { value: "all_with_ambiguous", label: "+ AMBIGUOUS" },
] as const;

export type ConfidenceOption = (typeof CONFIDENCE_OPTIONS)[number]["value"];
