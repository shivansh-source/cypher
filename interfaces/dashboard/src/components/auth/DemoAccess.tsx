"use client";

import { useActionState } from "react";
import { signInAsDemo, signUpAsDemo } from "@/app/(auth)/actions";
import { Spinner } from "@/components/Loader";
import type { DemoCredentials } from "@/lib/demo-account";

const MODES = {
  signin: {
    action: signInAsDemo,
    title: "Just exploring? Use the demo account",
    button: "Sign in as demo",
    pending: "Signing in…",
    note: null,
  },
  signup: {
    action: signUpAsDemo,
    title: "Just exploring? Sign up as the demo organisation",
    button: "Sign up as demo",
    pending: "Setting up…",
    note: "Skips the form and takes you to tool selection, starting from the demo organisation's tools.",
  },
} as const;

/**
 * The shared demo sign-in, shown openly, with a one-click way to use it: on sign-in it goes
 * straight to the dashboard, on register it walks through tool selection first. Either way the
 * demo organisation's own tools are restored first.
 */
export function DemoAccess({ demo, mode }: { demo: DemoCredentials; mode: keyof typeof MODES }) {
  const copy = MODES[mode];
  const [error, action, pending] = useActionState(copy.action, null);
  return (
    <section className="auth-demo" aria-labelledby="demo-title">
      <h2 id="demo-title">{copy.title}</h2>
      {copy.note ? <p className="small muted">{copy.note}</p> : null}
      <dl>
        <dt>Email</dt>
        <dd>
          <code>{demo.email}</code>
        </dd>
        <dt>Password</dt>
        <dd>
          <code>{demo.password}</code>
        </dd>
      </dl>
      {error ? (
        <p className="auth-err" role="alert">
          {error}
        </p>
      ) : null}
      <form action={action}>
        <button type="submit" className="btn auth-submit" disabled={pending}>
          {pending ? (
            <>
              <Spinner /> {copy.pending}
            </>
          ) : (
            copy.button
          )}
        </button>
      </form>
    </section>
  );
}
