import { NextResponse, type NextRequest } from "next/server";
import { decideRoute } from "@/lib/route-gate";
import { SESSION_COOKIE } from "@/lib/session-name";
import { sessionSecretConfigured, verifySessionToken } from "@/lib/token-claims";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface Standing {
  signedIn: boolean;
  onboarded: boolean;
  /** The cookie is present but no longer valid: clear it. */
  stale: boolean;
}

/**
 * Slow path: ask the API. Used only when this server has no `AUTH_JWT_SECRET`
 * to check the token itself, or for a token issued before it carried `onb`.
 * It costs a database round trip, so it must stay the exception.
 */
async function askApi(token: string): Promise<Standing> {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (res.ok) {
      const me = (await res.json()) as { org?: { onboarded?: boolean } };
      return { signedIn: true, onboarded: Boolean(me.org?.onboarded), stale: false };
    }
    if (res.status === 401) return { signedIn: false, onboarded: false, stale: true };
  } catch {
    // fall through
  }
  // API trouble: don't lock everyone out to /register; pages show their own errors.
  return { signedIn: true, onboarded: true, stale: false };
}

async function standing(token: string | undefined): Promise<Standing> {
  if (!token) return { signedIn: false, onboarded: false, stale: false };
  if (!sessionSecretConfigured()) return askApi(token);
  const claims = await verifySessionToken(token);
  if (!claims) return { signedIn: false, onboarded: false, stale: true };
  if (claims.onboarded === null) return askApi(token);
  return { signedIn: true, onboarded: claims.onboarded, stale: false };
}

/**
 * Request gate: sends visitors to register / setup / home according to
 * `decideRoute`. An optimistic check with no network call in the normal case —
 * the token's signature is verified locally. The API verifies it again on every
 * data request, so this is routing, not authorisation.
 */
export async function proxy(request: NextRequest) {
  const { signedIn, onboarded, stale } = await standing(request.cookies.get(SESSION_COOKIE)?.value);

  const decision = decideRoute(request.nextUrl.pathname, signedIn, onboarded);
  const target =
    decision === "to-register" ? "/register" : decision === "to-setup" ? "/setup?first=1" : decision === "to-home" ? "/" : null;
  const response = target ? NextResponse.redirect(new URL(target, request.url)) : NextResponse.next();
  if (stale) response.cookies.delete(SESSION_COOKIE);
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logos/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
