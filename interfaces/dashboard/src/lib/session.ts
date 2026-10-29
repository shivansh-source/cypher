import "server-only";
import { cookies } from "next/headers";
import { cache } from "react";
import { SESSION_COOKIE } from "./session-name";
import { verifySessionToken, type SessionClaims } from "./token-claims";

const SESSION_MAX_AGE_SECONDS = 7 * 24 * 3600;

/** The API's session token, kept in an httpOnly cookie so page scripts never read it directly. */
export async function getSessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

/** The verified claims of the current request's session, or `null`. Local check, no network. */
export const getSessionClaims = cache(async (): Promise<SessionClaims | null> => {
  const token = await getSessionToken();
  return token ? verifySessionToken(token) : null;
});

export async function setSessionToken(token: string): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
}

export async function clearSessionToken(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
