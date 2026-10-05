import "server-only";
import { accountCall } from "./account-api";

export interface DemoCredentials {
  email: string;
  password: string;
}

/**
 * The shared demo sign-in the API publishes (`GET /auth/demo`), or null when none is
 * configured or the API is unreachable. Public by design: it is shown on the sign-in and
 * register pages so nobody evaluating the dashboard has to create an account.
 */
export async function fetchDemoCredentials(): Promise<DemoCredentials | null> {
  const result = await accountCall<DemoCredentials>("/auth/demo");
  return result.ok ? result.data : null;
}
