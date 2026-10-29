/**
 * Pure routing decision for the request gate (`proxy.ts`), kept separate so it
 * can be unit-tested without Next or Supabase.
 */
export const PUBLIC_ROUTES = ["/login", "/register"];
export const SETUP_ROUTE = "/setup";

export type GateDecision = "allow" | "to-register" | "to-setup" | "to-home";

export function decideRoute(pathname: string, signedIn: boolean, onboarded: boolean): GateDecision {
  const isPublic = PUBLIC_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`));
  if (!signedIn) return isPublic ? "allow" : "to-register";
  if (isPublic) return onboarded ? "to-home" : "to-setup";
  if (!onboarded && !pathname.startsWith(SETUP_ROUTE)) return "to-setup";
  return "allow";
}

/**
 * Routes rendered on their own, outside the app frame: no sidebar, top bar or
 * Ask Cypher panel. Shared by `AppShell` and `Topbar` so they cannot disagree.
 */
export const STANDALONE_ROUTES = [SETUP_ROUTE, ...PUBLIC_ROUTES];

export function isStandaloneRoute(pathname: string): boolean {
  return STANDALONE_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`));
}
