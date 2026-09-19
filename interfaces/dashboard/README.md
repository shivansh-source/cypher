# `interfaces/dashboard/`

The Su₹aksha frontend. Bootstrapped with `create-next-app`
(TypeScript, App Router, Tailwind, ESLint) and currently unmodified from
that default template — `src/app/page.tsx` is still the stock starter
page. See the repo-root `CLAUDE.md` and `README.md` for the project this
app is part of.

## Boundary with the backend

This app is a separate Node.js project from the rest of the repo. It must:

- Talk to the backend **only** through the FastAPI app in
  `interfaces/api/app.py`, over HTTP — never by importing a Python module,
  reading a Python file, or reaching into `core/`/`governance/`/`ai/`
  directly.
- Never compute, adjust, or re-derive a rupee figure client-side. Every
  number it displays must come from a backend response, verbatim — the
  same "no invented numbers" rule that governs `ai/numeric_guard.py`
  applies here too: this UI is a renderer, not a second engine.

The backend must never import anything from this directory either — see
the module ownership map in the repo-root `CLAUDE.md`. Configure the
backend URL via an environment variable (e.g. `NEXT_PUBLIC_API_BASE_URL`)
rather than hardcoding it — see the `TODO` in `infra/docker-compose.yml`
for the placeholder name currently in use.

## TODO

- Build actual pages/components once the API's response shapes
  (`core.engine.RiskFigure`, `core.optimizer.PortfolioRecommendation`,
  `governance.mapper.ControlStatus`, etc.) are stable enough to type
  against. Nothing beyond the default `create-next-app` template exists
  yet.
- Add `infra/Dockerfile` for this app to match the `dashboard` service
  already stubbed in `infra/docker-compose.yml`.

---

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
