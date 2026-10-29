import { jwtVerify } from "jose";

/** What the API's session token carries (see `interfaces/api/auth.py::issue_token`). */
export interface SessionClaims {
  userId: string;
  orgId: string;
  orgName: string | null;
  entityType: string | null;
  /** `null` for a token issued before this claim existed: ask the API instead. */
  onboarded: boolean | null;
}

const AUDIENCE = "suraksha";

/** Server-side signing secret, shared with the API. Never a `NEXT_PUBLIC_` variable. */
export function sessionSecretConfigured(): boolean {
  return (process.env.AUTH_JWT_SECRET ?? "").length > 0;
}

/**
 * Verify a session token locally (signature, audience, expiry). No network:
 * this is what lets the request gate and the layout skip a database round trip.
 * Returns `null` for anything invalid, expired or unverifiable.
 */
export async function verifySessionToken(token: string): Promise<SessionClaims | null> {
  const secret = process.env.AUTH_JWT_SECRET ?? "";
  if (!secret) return null;
  try {
    const { payload } = await jwtVerify(token, new TextEncoder().encode(secret), {
      audience: AUDIENCE,
      algorithms: ["HS256"],
    });
    if (typeof payload.sub !== "string" || typeof payload.org !== "string") return null;
    return {
      userId: payload.sub,
      orgId: payload.org,
      orgName: typeof payload.org_name === "string" ? payload.org_name : null,
      entityType: typeof payload.etype === "string" ? payload.etype : null,
      onboarded: typeof payload.onb === "boolean" ? payload.onb : null,
    };
  } catch {
    return null;
  }
}
