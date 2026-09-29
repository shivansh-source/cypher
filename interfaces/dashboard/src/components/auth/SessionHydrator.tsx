"use client";

import { useEffect } from "react";
import { saveOrgProfile } from "@/lib/org-profile-state";
import { saveCustomTools, saveToolSelection, type CustomTool } from "@/lib/tool-selection-state";
import type { EntityType } from "@/lib/frameworks";

export interface HydrationState {
  name: string;
  entityType: EntityType | null;
  onboarded: boolean;
  toolIds: string[];
  customTools: CustomTool[];
}

/**
 * Makes the in-browser stores (which the whole dashboard reads) mirror what the
 * database holds for the signed-in organisation. Signed out (`state === null`)
 * it clears them, so one account's selection never shows under another.
 */
export function SessionHydrator({ state }: { state: HydrationState | null }) {
  useEffect(() => {
    if (!state) {
      saveToolSelection(null);
      saveCustomTools([]);
      saveOrgProfile(null);
      return;
    }
    saveToolSelection(state.onboarded ? state.toolIds : null);
    saveCustomTools(state.customTools);
    saveOrgProfile({ name: state.name, entityType: state.entityType });
  }, [state]);
  return null;
}
