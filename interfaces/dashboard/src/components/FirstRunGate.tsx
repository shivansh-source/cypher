"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useToolSelection } from "@/lib/tool-selection-state";

/**
 * Sends a browser that has never completed the tool-selector setup screen
 * there first, before anything else in the app.
 *
 * Renders nothing — this is a side effect only, and it does nothing until
 * `useToolSelection` has actually read `localStorage` (its `null` state),
 * so a browser that already saved a selection never flashes the setup
 * screen on the way to the page it asked for.
 */
export function FirstRunGate() {
  const pathname = usePathname();
  const router = useRouter();
  const selection = useToolSelection();

  useEffect(() => {
    if (selection === undefined && pathname !== "/setup") {
      router.replace("/setup?first=1");
    }
  }, [selection, pathname, router]);

  return null;
}
