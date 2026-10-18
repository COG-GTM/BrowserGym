import type { components } from "./generated/openapi";

type Schemas = components["schemas"];

export type Run = Schemas["Run"];
export type RunStatus = Schemas["RunStatus"];
export type Step = Schemas["Step"];
export type StepDetail = Schemas["StepDetail"];
export type ChatMessage = Schemas["ChatMessage"];
export type AgentConfig = Schemas["AgentConfig"];

/**
 * Bounding box of a BrowserGym element in screenshot pixel coordinates.
 * `bbox` is `[x, y, width, height]`, matching `extra_element_properties[bid].bbox`.
 */
export interface ElementBox {
  bid: string;
  bbox: [number, number, number, number];
  clickable?: boolean;
  /** Element is part of the Set-of-Marks (SOM) subset. */
  som?: boolean;
}

/** Shape of BrowserGym's `obs["extra_element_properties"]`. */
export type ExtraElementProperties = Record<
  string,
  {
    visibility?: number;
    bbox?: number[] | null;
    clickable?: boolean;
    set_of_marks?: boolean | number;
  }
>;
