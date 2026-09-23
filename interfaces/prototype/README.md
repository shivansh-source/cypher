# Su₹aksha dashboard prototype

A standalone, dependency-free prototype of the Su₹aksha dashboard (SIH 2026,
PS 26105). It runs a small Open FAIR + Monte Carlo engine in the browser
against a **sample reference NBFC**, so every chart on the page is computed
rather than hard-coded. It is a design and interaction prototype for the real
Next.js app in `interfaces/dashboard/`, not a replacement for it.

> **Sample data.** The assets, findings, EPSS scores and costs are illustrative.
> Loss magnitudes follow US-calibrated ranges (Cyentia IRIS) until the Indian
> incident corpus exists; business criticality and downtime costs are declared
> inputs. The page says so on every view.

## Run it

No build step and no packages. Serve the folder with any static server:

```
cd interfaces/prototype
python -m http.server 8080
```

Then open http://localhost:8080. Fonts (Poppins, Inter) load from Google
Fonts; offline the page falls back to system fonts.

## What is on it

| View | Contents |
|---|---|
| Overview | Expected annual loss, VaR 95%, exposure vs risk appetite, best use of ₹1 Cr; loss-over-time chart by vulnerability or loss type with an 8-week forecast (planned fixes vs a 30-day delay); loss exceedance curve; top contributors; what-if scenarios; accrued loss per open finding; business-unit roll-up |
| Assets & findings | Asset table with control chips, per-asset FAIR parameters and provenance, remediation backlog with cost per day of delay |
| Investment | Budget slider, investment vs risk-reduction frontier over 1,024 jointly simulated portfolios, ROSI, naive-sum vs joint-simulation callout |
| Compliance | RBI Directions 2026, SEBI CSCRF, CIS v8.1, NIST CSF 2.0, ISO 27001:2022, DPDP Act 2023: status from evidence, linked findings, statutory exposure |
| Data & model | Five quality gates and their history, connector freshness, sensitivity, lab-measured EDR efficacy, identity resolution queue, conflict register C1–C6, assumption register |
| Ask Suraksha | Pop-up assistant that routes a question to an engine tool and renders the tool's output; the source and verification details are one click away |

## How it maps to the repo's design principles

- **The rupee figure comes from the engine** (`js/engine.js`). Ask Suraksha
  only picks a tool and fills a template with engine output (principles 1–2).
- **Correlation is modelled**: shared control-health factors are drawn once per
  simulated year and applied to every scenario that depends on that control
  (conflict C3).
- **Portfolios are re-simulated jointly** (`js/optimizer.js`); the investment
  view shows how much a naive sum of per-control benefits would overstate the
  result (principle 7, conflict C4).
- **Compliance maps to evidence**, never to optimizer output (principle 6).
- **Quality gates hold the previous snapshot** when a candidate fails; the
  hatched week on the loss chart shows one such rejection (principle 4).
- **Same snapshot, same figure**: the random draws come from a fixed seed, and
  what-if scenarios reuse the baseline's draws so differences come from the
  change, not from noise.

## Layout

```
index.html        Markup for the shell and every view
css/              One stylesheet per concern, loaded in cascade order
js/               Classic scripts sharing one global scope, loaded in order:
  format.js       Formatting helpers
  data.js         Sample reference environment
  engine.js       Open FAIR + Monte Carlo engine, snapshot history, forecast
  dom.js          SVG, tooltip and legend helpers
  optimizer.js    Joint re-simulation over every candidate portfolio
  overview.js     Overview charts and KPIs
  scenarios.js    What-if scenario lab
  shell.js        Sidebar collapse and snapshot id
  ask.js          Ask Suraksha assistant and modal
  assets.js       Assets & findings view
  investment.js   Investment view
  compliance.js   Compliance view
  data-model.js   Data & model view
  app.js          Routing and wiring (must load last)
```

Light and dark themes follow the operating system setting.
