"use client";

import Link from "next/link";
import { useActionState } from "react";
import { login, type AuthFormState } from "@/app/(auth)/actions";
import { Spinner } from "@/components/Loader";
import { AuthField, PasswordField } from "./AuthField";

const INITIAL: AuthFormState = { error: null, fieldErrors: {}, values: { orgName: "", email: "" } };

export function LoginForm() {
  const [state, action, pending] = useActionState(login, INITIAL);
  return (
    <form action={action} className="auth-form" noValidate>
      <h1>Welcome back</h1>
      <p className="auth-sub">Sign in to see your organisation&apos;s risk in rupees.</p>
      {state.error ? <div className="auth-banner" role="alert">{state.error}</div> : null}
      <AuthField label="Work email" name="email" type="email" autoComplete="email" required defaultValue={state.values.email} />
      <PasswordField autoComplete="current-password" />
      <button type="submit" className="btn auth-submit" disabled={pending}>
        {pending ? (
          <>
            <Spinner /> Signing in…
          </>
        ) : (
          "Sign in"
        )}
      </button>
      <p className="auth-alt">
        New to Cypher? <Link href="/register">Create an account</Link>
      </p>
    </form>
  );
}
