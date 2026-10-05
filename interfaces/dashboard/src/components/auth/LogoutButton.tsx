"use client";

import { useFormStatus } from "react-dom";
import { logout } from "@/app/(auth)/actions";
import { Spinner } from "@/components/Loader";

/** Submit button for the sign-out form; shows progress while the request is in flight. */
function LogoutSubmit() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="btn ghost signout" disabled={pending}>
      {pending ? (
        <>
          <Spinner size={12} /> Signing out…
        </>
      ) : (
        <>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10" />
          </svg>
          Sign out
        </>
      )}
    </button>
  );
}

/** A visible "Sign out" button: clears the session cookie and returns to /login. */
export function LogoutButton() {
  return (
    <form action={logout}>
      <LogoutSubmit />
    </form>
  );
}
