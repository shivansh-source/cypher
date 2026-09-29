import { NextResponse, type NextRequest } from "next/server";
import { decideRoute } from "@/lib/route-gate";
import { SESSION_COOKIE } from "@/lib/session-name";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * Request gate: sends visitors to register / setup / home according to
 * `decideRoute`. An optimistic check — the API verifies the token on every
 * data request itself.
 */
export async function proxy(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  let signedIn = false;
  let onboarded = false;
  let staleCookie = false;

  if (token) {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (res.ok) {
        const me = (await res.json()) as { org?: { onboarded?: boolean } };
        signedIn = true;
        onboarded = Boolean(me.org?.onboarded);
      } else if (res.status === 401) {
        staleCookie = true; // expired, or the account was deleted
      } else {
        signedIn = onboarded = true; // API trouble (503...): let pages show their own errors
      }
    } catch {
      signedIn = onboarded = true; // API unreachable: don't lock everyone out to /register
    }
  }

  const decision = decideRoute(request.nextUrl.pathname, signedIn, onboarded);
  const target =
    decision === "to-register" ? "/register" : decision === "to-setup" ? "/setup?first=1" : decision === "to-home" ? "/" : null;
  const response = target ? NextResponse.redirect(new URL(target, request.url)) : NextResponse.next();
  if (staleCookie) response.cookies.delete(SESSION_COOKIE);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logos/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
