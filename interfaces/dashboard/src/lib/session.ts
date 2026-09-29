import "server-only";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "./session-name";

const SESSION_MAX_AGE_SECONDS = 7 * 24 * 3600;

/** The API's session token, kept in an httpOnly cookie so page scripts never read it directly. */
export async function getSessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

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
