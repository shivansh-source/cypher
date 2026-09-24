import Link from "next/link";

/**
 * The standing caveat under every page title: what the figures rest on.
 *
 * The prototype's caveat named a sample organization; the real dashboard's
 * caveat names the real limitation — every modelling constant in
 * core/assumptions.py is an uncalibrated placeholder.
 */
export function Caveat() {
  return (
    <div className="caveat" role="note">
      <span aria-hidden="true" style={{ color: "var(--marigold)", fontWeight: 700 }}>
        !
      </span>
      <p>
        <strong>Figures come from a deterministic Open FAIR + Monte Carlo engine, never from a model.</strong>{" "}
        They rest on the named constants in <code>core/assumptions.py</code> — threat
        frequencies, control strengths and loss magnitudes — which are{" "}
        <strong>uncalibrated placeholders</strong>, not measurements. Read any figure
        alongside them.{" "}
        <Link className="linkbtn" href="/data-quality#assumptions">
          See every assumption
        </Link>
      </p>
    </div>
  );
}
