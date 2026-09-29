/** Minimum length Supabase is configured to accept; keep in sync with the project's auth settings. */
export const MIN_PASSWORD_LENGTH = 10;

export interface PasswordStrength {
  /** 0 (empty) .. 4 (strong). */
  score: 0 | 1 | 2 | 3 | 4;
  label: "" | "Too short" | "Weak" | "Fair" | "Good" | "Strong";
  acceptable: boolean;
}

/** Cheap, dependency-free strength hint: length plus character variety. */
export function passwordStrength(password: string): PasswordStrength {
  if (password.length === 0) return { score: 0, label: "", acceptable: false };
  if (password.length < MIN_PASSWORD_LENGTH) return { score: 1, label: "Too short", acceptable: false };
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(password)).length;
  const long = password.length >= 14;
  const points = classes + (long ? 1 : 0);
  if (points <= 2) return { score: 2, label: "Weak", acceptable: false };
  if (points === 3) return { score: 3, label: "Fair", acceptable: true };
  if (points === 4) return { score: 3, label: "Good", acceptable: true };
  return { score: 4, label: "Strong", acceptable: true };
}
