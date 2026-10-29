import { Suspense } from "react";
import { redirect } from "next/navigation";
import { PageLoader } from "@/components/Loader";
import { loadOrgState } from "@/lib/org-repo";
import { SetupScreen } from "./SetupScreen";

/**
 * Onboarding: which security tools the org runs. The form starts from what is
 * stored for the organisation (one database read, only on this page); the
 * request gate has already sent signed-out visitors to /register.
 */
export default async function SetupPage() {
  const initial = await loadOrgState();
  if (!initial) redirect("/login");
  return (
    <Suspense fallback={<PageLoader label="Loading…" fill />}>
      <SetupScreen initial={initial} />
    </Suspense>
  );
}
