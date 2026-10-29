"use client";

import Link from "next/link";
import { useActionState } from "react";
import { register, type AuthFormState } from "@/app/(auth)/actions";
import { Spinner } from "@/components/Loader";
import { AuthField, PasswordField } from "./AuthField";

const INITIAL: AuthFormState = { error: null, fieldErrors: {}, values: { orgName: "", email: "" } };

export function RegisterForm() {
  const [state, action, pending] = useActionState(register, INITIAL);
  return (
    <form action={action} className="auth-form" noValidate>
      <h1>Create your account</h1>
      <p className="auth-sub">Start with your organisation. You&apos;ll pick your security tools next.</p>
      {state.error ? <div className="auth-banner" role="alert">{state.error}</div> : null}
      <AuthField
        label="Organisation name"
        name="orgName"
        autoComplete="organization"
        required
        maxLength={120}
        defaultValue={state.values.orgName}
        error={state.fieldErrors.orgName}
      />
      <AuthField
        label="Work email"
        name="email"
        type="email"
        autoComplete="email"
        required
        defaultValue={state.values.email}
        error={state.fieldErrors.email}
      />
      <PasswordField autoComplete="new-password" meter error={state.fieldErrors.password} />
      <button type="submit" className="btn auth-submit" disabled={pending}>
        {pending ? (
          <>
            <Spinner /> Creating account…
          </>
        ) : (
          "Create account"
        )}
      </button>
      <p className="auth-alt">
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </form>
  );
}
