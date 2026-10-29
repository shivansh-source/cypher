/**
 * The signed-in user's session token, for the API's `Authorization` header.
 *
 * On the server it is read straight from the request cookie. In the browser the
 * cookie is httpOnly, so a server action returns it; that is a network round
 * trip, so the answer is kept for the life of the page and every later API call
 * reuses it. `invalidateAccessToken()` drops it when the API says it is no
 * longer valid. `null` when signed out.
 */
let browserToken: Promise<string | null> | null = null;

export function invalidateAccessToken(): void {
  browserToken = null;
}

export async function getAccessToken(): Promise<string | null> {
  const { serverAccessToken } = await import("./server-token");
  if (typeof window === "undefined") {
    try {
      return await serverAccessToken();
    } catch {
      return null;
    }
  }
  browserToken ??= serverAccessToken().catch(() => {
    browserToken = null; // let the next call try again rather than caching a failure
    return null;
  });
  return browserToken;
}
