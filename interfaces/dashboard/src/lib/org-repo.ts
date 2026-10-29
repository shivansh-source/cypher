import "server-only";
import { accountCall, type AccountResponse } from "@/lib/account-api";
import { ENTITY_TYPES, type EntityType } from "@/lib/frameworks";
import { getSessionToken } from "@/lib/session";
import { CATEGORY_ORDER } from "@/lib/tool-catalog";
import type { CustomTool } from "@/lib/tool-selection-state";

/** What the database holds for the signed-in user's organisation. */
export interface OrgState {
  email: string;
  /** ISO timestamp the user registered, when the API reports it. */
  memberSince: string | null;
  name: string;
  entityType: EntityType | null;
  onboarded: boolean;
  toolIds: string[];
  customTools: CustomTool[];
}

/** Loads the signed-in user's org and tools, or `null` when signed out (or the API is down). */
export async function loadOrgState(): Promise<OrgState | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const result = await accountCall<AccountResponse>("/auth/me", { token });
  if (!result.ok) return null;
  const { email, member_since, org, tools } = result.data;
  return {
    email,
    memberSince: member_since ?? null,
    name: org.name,
    entityType: ENTITY_TYPES.find((t) => t.id === org.entity_type)?.id ?? null,
    onboarded: org.onboarded,
    toolIds: tools.map((t) => t.tool_id),
    customTools: tools.flatMap((t) => {
      const category = CATEGORY_ORDER.find((c) => c === t.category);
      return t.is_custom && t.custom_name && category ? [{ id: t.tool_id, name: t.custom_name, category }] : [];
    }),
  };
}
