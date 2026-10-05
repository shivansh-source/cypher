import type { Metadata } from "next";
import { AuthShell } from "@/components/auth/AuthShell";
import { LoginForm } from "@/components/auth/LoginForm";
import { DemoAccess } from "@/components/auth/DemoAccess";
import { fetchDemoCredentials } from "@/lib/demo-account";

export const metadata: Metadata = { title: "Sign in · Cypher" };

export default async function LoginPage() {
  const demo = await fetchDemoCredentials();
  return (
    <AuthShell>
      {demo ? <DemoAccess demo={demo} mode="signin" /> : null}
      <LoginForm />
    </AuthShell>
  );
}
