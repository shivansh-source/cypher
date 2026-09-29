import type { Metadata } from "next";
import { AuthShell } from "@/components/auth/AuthShell";
import { RegisterForm } from "@/components/auth/RegisterForm";

export const metadata: Metadata = { title: "Create account · Cypher" };

export default function RegisterPage() {
  return (
    <AuthShell step={1}>
      <RegisterForm />
    </AuthShell>
  );
}
