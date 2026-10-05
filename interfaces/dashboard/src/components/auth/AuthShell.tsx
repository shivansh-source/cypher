import type { ReactNode } from "react";
import { CypherMark } from "@/components/CypherMark";

const STEPS = ["Account", "Tools", "Dashboard"];

const PROOFS = [
  { title: "Open FAIR + Monte Carlo", body: "Every rupee figure comes from a deterministic engine, never a model's guess." },
  { title: "Mapped to Indian regulation", body: "RBI Directions 2026, SEBI CSCRF, CIS, NIST CSF and ISO 27001." },
  { title: "Spend the budget where it counts", body: "Controls are re-simulated together, so overlaps never inflate the benefit." },
];

/** Split layout for sign-in / register: brand story on the left, form card on the right. */
export function AuthShell({ step, children }: { step?: 1 | 2 | 3; children: ReactNode }) {
  return (
    <div className="auth">
      <aside className="auth-brand" aria-hidden={false}>
        <div className="brand">
          <div className="mark" aria-hidden="true">
            <CypherMark />
          </div>
          <div className="word">Cypher</div>
        </div>
        <div className="auth-hero">
          {/* The product mark: white line art on transparency (public/cypher-mark.png, from cypher.png). */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/cypher-mark.png" alt="Cypher" width={900} height={634} fetchPriority="high" />
        </div>
        <div className="auth-story">
          <h2>Put a rupee figure on your cyber risk.</h2>
          <ul>
            {PROOFS.map((p) => (
              <li key={p.title}>
                <b>{p.title}</b>
                <span>{p.body}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
      <div className="auth-panel">
        <div className="auth-card">
          {step ? (
            <ol className="auth-steps" aria-label="Setup progress">
              {STEPS.map((label, i) => (
                <li key={label} aria-current={i + 1 === step ? "step" : undefined} className={i + 1 <= step ? "on" : ""}>
                  <span>{i + 1}</span>
                  {label}
                </li>
              ))}
            </ol>
          ) : null}
          {children}
        </div>
      </div>
    </div>
  );
}
