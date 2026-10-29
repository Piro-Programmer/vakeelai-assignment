// Copies dist/index.html to dist/<route>/index.html for every client-side route.
// Why: on Vercel's multi-service setup the static frontend has no SPA fallback,
// so a direct visit or refresh on /cases returned 404. Real files at those paths
// work on any static host, with no host-specific rewrite rules.
import { copyFileSync, mkdirSync } from 'node:fs'

const ROUTES = ['cases', 'drafts'] // keep in sync with <Routes> in src/App.tsx
for (const r of ROUTES) {
  mkdirSync(`dist/${r}`, { recursive: true })
  copyFileSync('dist/index.html', `dist/${r}/index.html`)
}
console.log(`SPA route shells written: ${ROUTES.join(', ')}`)
