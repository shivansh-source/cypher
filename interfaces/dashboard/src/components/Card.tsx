import type { ReactNode } from "react";
import { SampleTag } from "./DemoBanner";

/**
 * A titled section container — the dashboard's one structural unit.
 *
 * Carries a `SAMPLE` tag in its title in demo mode, so every panel of figures
 * is labelled, not only the headline ones.
 */
export function Card({
  title,
  subtitle,
  actions,
  id,
  className,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  id?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`card${className ? ` ${className}` : ""}`} id={id}>
      <div className="card-h">
        <div>
          <h2>
            {title}
            <SampleTag />
          </h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
