import { InvestmentPlanner } from "@/components/InvestmentPlanner";
import { Unavailable } from "@/components/Unavailable";
import { fetchControlGaps } from "@/lib/api";

export default async function InvestmentPage() {
  const candidates = await fetchControlGaps();

  if (candidates.state !== "ok") {
    return <Unavailable result={candidates} what="candidate controls" />;
  }

  if (candidates.data.gaps.length === 0) {
    return (
      <section className="card">
        <h2>Nothing to fund</h2>
        <p className="small muted" style={{ marginTop: 6 }}>
          Every control the engine can model ({candidates.data.applicable_categories.join(", ")}) is
          already observed active on every asset in the current snapshot, so there is no candidate
          for the optimizer to consider.
        </p>
      </section>
    );
  }

  return <InvestmentPlanner candidates={candidates.data} />;
}
