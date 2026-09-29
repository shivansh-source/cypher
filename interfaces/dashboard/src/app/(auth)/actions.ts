"use server";

import { redirect } from "next/navigation";
import { MIN_PASSWORD_LENGTH, passwordStrength } from "@/lib/password-strength";
import { accountCall } from "@/lib/account-api";
import { clearSessionToken, getSessionToken, setSessionToken } from "@/lib/session";
import { ENTITY_TYPES, type EntityType } from "@/lib/frameworks";
import { CATEGORY_ORDER, type ToolCategory } from "@/lib/tool-catalog";

export interface AuthFormState {
  error: string | null;
  fieldErrors: Partial<Record<"orgName" | "email" | "password", string>>;
  /** Echoed back so a failed submit doesn't clear what was typed (never the password). */
  values: { orgName: string; email: string };
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_ORG_NAME = 120;

interface TokenResponse {
  token: string;
}

function text(form: FormData, key: string): string {
  const v = form.get(key);
  return typeof v === "string" ? v : "";
}

export async function register(_prev: AuthFormState, form: FormData): Promise<AuthFormState> {
  const orgName = text(form, "orgName").trim();
  const email = text(form, "email").trim().toLowerCase();
  const password = text(form, "password");
  const fieldErrors: AuthFormState["fieldErrors"] = {};

  if (!orgName) fieldErrors.orgName = "Enter your organisation's name.";
  else if (orgName.length > MAX_ORG_NAME) fieldErrors.orgName = `Keep it under ${MAX_ORG_NAME} characters.`;
  if (!EMAIL_RE.test(email)) fieldErrors.email = "Enter a valid work email.";
  if (!passwordStrength(password).acceptable) {
    fieldErrors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters with a mix of letters, numbers or symbols.`;
  }
  const values = { orgName, email };
  if (Object.keys(fieldErrors).length > 0) return { error: null, fieldErrors, values };

  const result = await accountCall<TokenResponse>("/auth/register", {
    method: "POST",
    body: { org_name: orgName, email, password },
  });
  if (!result.ok) {
    if (result.status === 409) {
      return { error: "An account with this email already exists. Try signing in.", fieldErrors: {}, values };
    }
    if (result.status === 422) {
      return {
        error: null,
        fieldErrors: { orgName: result.fields.org_name, email: result.fields.email, password: result.fields.password },
        values,
      };
    }
    return { error: result.detail, fieldErrors: {}, values };
  }
  await setSessionToken(result.data.token);
  redirect("/setup?first=1");
}

export async function login(_prev: AuthFormState, form: FormData): Promise<AuthFormState> {
  const email = text(form, "email").trim().toLowerCase();
  const password = text(form, "password");
  const values = { orgName: "", email };
  if (!email || !password) {
    return { error: "Enter your email and password.", fieldErrors: {}, values };
  }
  const result = await accountCall<TokenResponse>("/auth/login", { method: "POST", body: { email, password } });
  if (!result.ok) {
    // One message for every credential failure; only infrastructure errors say more.
    const error = result.status === 401 ? "Incorrect email or password." : result.detail;
    return { error, fieldErrors: {}, values };
  }
  await setSessionToken(result.data.token);
  redirect("/");
}

export async function logout(): Promise<void> {
  await clearSessionToken();
  redirect("/login");
}

export interface SetupPayload {
  entityType: EntityType | null;
  tools: { id: string; name?: string; category?: ToolCategory }[];
}

/** Persists the tool-selection step and marks onboarding complete. */
export async function saveSetup(payload: SetupPayload): Promise<{ ok: boolean; error?: string }> {
  const entity = ENTITY_TYPES.find((t) => t.id === payload.entityType)?.id ?? null;
  const tools = payload.tools.slice(0, 200).map((t) => ({
    id: t.id.slice(0, 80),
    name: t.id.startsWith("custom:") ? (t.name ?? "").trim().slice(0, 120) : undefined,
    category: t.id.startsWith("custom:") && t.category && CATEGORY_ORDER.includes(t.category) ? t.category : undefined,
  }));
  const result = await accountCall<{ ok: boolean }>("/org/setup", {
    method: "POST",
    body: { entity_type: entity, tools },
    token: await getSessionToken(),
  });
  if (!result.ok) {
    return { ok: false, error: result.status === 401 ? "Your session expired. Please sign in again." : result.detail };
  }
  return { ok: true };
}
