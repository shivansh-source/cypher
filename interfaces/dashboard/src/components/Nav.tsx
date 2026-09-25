"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const LINKS: { href: string; label: string; icon: ReactNode }[] = [
  {
    href: "/",
    label: "Overview",
    icon: (
      <>
        <path d="M3 12l9-8 9 8" />
        <path d="M5 10v10h14V10" />
      </>
    ),
  },
  {
    href: "/assets",
    label: "Assets & findings",
    icon: (
      <>
        <rect x="3" y="4" width="18" height="6" rx="1.5" />
        <rect x="3" y="14" width="18" height="6" rx="1.5" />
        <path d="M7 7h.01M7 17h.01" />
      </>
    ),
  },
  {
    href: "/investment",
    label: "Investment",
    icon: (
      <>
        <path d="M4 19V5" />
        <path d="M4 19h16" />
        <path d="M7 15l4-5 3 3 5-7" />
      </>
    ),
  },
  {
    href: "/compliance",
    label: "Compliance",
    icon: (
      <>
        <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
        <path d="M9 12l2 2 4-4" />
      </>
    ),
  },
  {
    href: "/data-quality",
    label: "Data & coverage",
    icon: (
      <>
        <ellipse cx="12" cy="6" rx="8" ry="3" />
        <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
        <path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </>
    ),
  },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav" id="sideNav" aria-label="Views">
      {LINKS.map((link) => {
        const active =
          link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            title={link.label}
            aria-current={active ? "page" : undefined}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              {link.icon}
            </svg>
            <span className="t">{link.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
