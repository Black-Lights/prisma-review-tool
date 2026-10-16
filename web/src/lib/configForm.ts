/**
 * Pure helpers for the Settings form: masked API keys, optimistic concurrency
 * on PUT /api/config (the `_version` contract) and small config checks. Kept
 * free of React so they can be unit tested with `node --test`.
 */
import type { ConfigData } from "./api";

/** What GET /api/config sends instead of a stored API key value. */
export const SECRET_MASK = "********";

// api_keys entries that are not secrets (the API returns them as-is).
// Mirrors prisma_review/config.py PUBLIC_API_KEY_FIELDS.
export const PUBLIC_KEY_FIELDS: readonly string[] = ["openalex_email"];

/** Text shown in a secret input: never the mask, so typing cannot append to it. */
export function secretDisplayValue(value: unknown): string {
  return value === SECRET_MASK || typeof value !== "string" ? "" : value;
}

/**
 * Draft value after the user typed `typed` into a secret input whose server
 * value is `stored`. Emptying the box brings a stored key back (the mask means
 * "keep" on save); removing a key is a separate, explicit action.
 */
export function secretInputValue(typed: string, stored: unknown): string {
  return typed === "" && stored === SECRET_MASK ? SECRET_MASK : typed;
}

export type SecretState = "unset" | "stored" | "new" | "removed";

export function secretState(value: unknown, stored: unknown): SecretState {
  if (value === SECRET_MASK) return "stored";
  if (typeof value === "string" && value !== "") return "new";
  return stored === SECRET_MASK ? "removed" : "unset";
}

/** A copy with every non-public, non-empty API key replaced by the mask. */
export function maskSecrets(config: ConfigData): ConfigData {
  const out = structuredClone(config);
  const keys = out.api_keys;
  if (keys && typeof keys === "object") {
    for (const [field, value] of Object.entries(keys)) {
      if (!PUBLIC_KEY_FIELDS.includes(field) && value !== null && value !== undefined && value !== "") {
        keys[field] = SECRET_MASK;
      }
    }
  }
  return out;
}

/** The PUT body: the draft with the `_version` it was based on (none if unknown). */
export function savePayload(draft: ConfigData, version: string | null | undefined): ConfigData {
  const out = structuredClone(draft);
  delete out._version;
  if (version) out._version = version;
  return out;
}

export interface ConfigConflict {
  message: string;
  currentVersion: string | null;
}

/** The 409 "config_changed" refusal of PUT /api/config, or null for any other error. */
export function configConflict(err: unknown): ConfigConflict | null {
  if (!err || typeof err !== "object") return null;
  const { status, detail } = err as { status?: unknown; detail?: unknown };
  if (status !== 409 || !detail || typeof detail !== "object") return null;
  const d = detail as { error?: unknown; message?: unknown; current_version?: unknown };
  if (d.error !== "config_changed") return null;
  return {
    message: typeof d.message === "string" ? d.message : "The config changed on disk.",
    currentVersion: typeof d.current_version === "string" ? d.current_version : null,
  };
}

/** Milliseconds since the epoch encoded in a config `_version` ("<mtime_ns>-<size>"). */
export function versionMtimeMs(version: string | null | undefined): number | null {
  const m = /^(\d+)-\d+$/.exec(version ?? "");
  if (!m) return null;
  const ns = m[1];
  return ns.length > 6 ? Number(ns.slice(0, -6)) : 0;
}

/** True when the config file was written after `isoTime` (e.g. the last run's start). */
export function configEditedSince(version: string | null | undefined, isoTime: string | null | undefined): boolean {
  const mtime = versionMtimeMs(version);
  const at = Date.parse(isoTime ?? "");
  return mtime !== null && !Number.isNaN(at) && mtime > at;
}

/** Split selected document types into the ones the UI offers and any others. */
export function splitDocTypes(
  selected: readonly string[] | undefined,
  known: readonly string[],
): { known: string[]; unknown: string[] } {
  const list = Array.isArray(selected) ? selected : [];
  return {
    known: list.filter((t) => known.includes(t)),
    unknown: list.filter((t) => !known.includes(t)),
  };
}
