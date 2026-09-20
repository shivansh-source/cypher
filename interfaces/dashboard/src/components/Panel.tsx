import type { ReactNode } from "react";

/** A titled section container — the dashboard's one structural unit. */
export function Panel({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3.5">
        <div>
          <h2 className="text-sm font-semibold tracking-wide text-ink uppercase">
            {title}
          </h2>
          {subtitle ? (
            <p className="mt-1 text-xs text-muted">{subtitle}</p>
          ) : null}
        </div>
        {actions}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}
