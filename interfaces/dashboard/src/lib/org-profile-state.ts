"use client";

import { ENTITY_TYPES, type EntityType } from "./frameworks";
import { createLocalStore } from "./local-store";

/**
 * Who this org is, as it told the setup screen: saved in this browser only,
 * like the tool selection (see `tool-selection-state.ts`). Nothing on the
 * backend reads it; the dashboard uses it to greet the org by name and to
 * say which regulatory frameworks apply to it.
 */
export interface OrgProfile {
  name: string;
  /** `null` when the org has not said. */
  entityType: EntityType | null;
}

const profile = createLocalStore<OrgProfile>("suraksha.org.profile", (raw) => {
  if (typeof raw !== "object" || raw === null) return undefined;
  const { name, entityType } = raw as Record<string, unknown>;
  if (typeof name !== "string") return undefined;
  const type = ENTITY_TYPES.find((t) => t.id === entityType)?.id ?? null;
  return { name, entityType: type };
});

export function saveOrgProfile(value: OrgProfile | null): void {
  profile.save(value);
}

/** The saved profile; `null` before the browser value is known, `undefined` if never saved. */
export function useOrgProfile(): OrgProfile | undefined | null {
  return profile.use();
}
