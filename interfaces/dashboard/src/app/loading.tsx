import { PageLoader } from "@/components/Loader";

/** Shown while a page's server data (the engine's figures) is being fetched. */
export default function Loading() {
  return <PageLoader label="Loading…" />;
}
