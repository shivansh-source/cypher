"use server";

import { getSessionToken } from "@/lib/session";

/**
 * The session token from the request cookie. A server action so client code
 * (`lib/api.ts`) can attach it as `Authorization: Bearer` without `next/headers`
 * reaching the browser bundle. `null` when signed out.
 */
export async function serverAccessToken(): Promise<string | null> {
  return getSessionToken();
}
