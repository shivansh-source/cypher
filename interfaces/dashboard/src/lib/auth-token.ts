/**
 * The signed-in user's session token, for the API's `Authorization` header.
 * Works in server components (reads the request cookie directly) and in the
 * browser (asks a server action, since the cookie is httpOnly). `null` when
 * signed out.
 */
export async function getAccessToken(): Promise<string | null> {
  const { serverAccessToken } = await import("./server-token");
  try {
    return await serverAccessToken();
  } catch {
    return null;
  }
}
