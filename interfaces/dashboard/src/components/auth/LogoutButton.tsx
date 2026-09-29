"use client";

import { useFormStatus } from "react-dom";
import { Spinner } from "@/components/Loader";

/** Submit button for the sign-out form; shows progress while the request is in flight. */
export function LogoutButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="linkbtn side-logout" disabled={pending}>
      {pending ? (
        <>
          <Spinner size={12} /> Signing out…
        </>
      ) : (
        "Sign out"
      )}
    </button>
  );
}
