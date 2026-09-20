"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Exposure" },
  { href: "/investment", label: "Investment" },
  { href: "/compliance", label: "Compliance" },
  { href: "/data-quality", label: "Data quality" },
] as const;

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1" aria-label="Primary">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              active
                ? "bg-surface-2 text-ink"
                : "text-muted hover:bg-surface-2 hover:text-ink"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
