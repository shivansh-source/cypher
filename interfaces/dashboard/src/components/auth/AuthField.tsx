"use client";

import { useId, useState, type InputHTMLAttributes } from "react";
import { passwordStrength } from "@/lib/password-strength";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export function AuthField({ label, error, hint, id, ...input }: FieldProps) {
  const auto = useId();
  const fid = id ?? auto;
  const describedBy = [error ? `${fid}-err` : null, hint ? `${fid}-hint` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="auth-field">
      <label htmlFor={fid}>{label}</label>
      <input id={fid} suppressHydrationWarning aria-invalid={error ? true : undefined} aria-describedby={describedBy} {...input} />
      {hint ? <p id={`${fid}-hint`} className="auth-hint">{hint}</p> : null}
      {error ? <p id={`${fid}-err`} className="auth-err" role="alert">{error}</p> : null}
    </div>
  );
}

/** Password input with a show/hide toggle and, on register, a live strength meter. */
export function PasswordField({
  label = "Password",
  error,
  meter = false,
  autoComplete,
  name = "password",
}: {
  label?: string;
  error?: string;
  meter?: boolean;
  autoComplete: string;
  name?: string;
}) {
  const fid = useId();
  const [shown, setShown] = useState(false);
  const [value, setValue] = useState("");
  const strength = passwordStrength(value);
  return (
    <div className="auth-field">
      <label htmlFor={fid}>{label}</label>
      <div className="auth-pw">
        <input
          id={fid}
          suppressHydrationWarning
          name={name}
          type={shown ? "text" : "password"}
          autoComplete={autoComplete}
          required
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fid}-err` : meter ? `${fid}-meter` : undefined}
        />
        <button type="button" className="auth-eye" aria-pressed={shown} onClick={() => setShown((s) => !s)}>
          {shown ? "Hide" : "Show"}
        </button>
      </div>
      {meter ? (
        <div id={`${fid}-meter`} className="auth-meter" data-score={strength.score} aria-live="polite">
          <span className="bars" aria-hidden="true">
            <i /><i /><i /><i />
          </span>
          <span className="lbl">{strength.label || "At least 10 characters, mixing letters, numbers or symbols"}</span>
        </div>
      ) : null}
      {error ? <p id={`${fid}-err`} className="auth-err" role="alert">{error}</p> : null}
    </div>
  );
}
