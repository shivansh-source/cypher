import type { Metadata } from "next";
import { AuthShell } from "@/components/auth/AuthShell";
import { RegisterForm } from "@/components/auth/RegisterForm";
import { DemoAccess } from "@/components/auth/DemoAccess";
import { fetchDemoCredentials } from "@/lib/demo-account";

export const metadata: Metadata = { title: "Create account · Cypher" };

export default async function RegisterPage() {
  const demo = await fetchDemoCredentials();
  return (
    <AuthShell step={1}>
      {demo ? <DemoAccess demo={demo} mode="signup" /> : null}
      <RegisterForm />
    </AuthShell>
  );
}
