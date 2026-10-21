# Prototype Instructions

## Approved visual direction (2026-10-21)

Preserve the refined atelier design: equal-size three-column project grid; ink-green navigation, ivory content, pale celadon asset rail, restrained gold botanical ornament. Traditional craft imagery comes from the repository's documented source photos, not fabricated specimen thumbnails. Use serif Chinese headings and quiet sans-serif controls. The user explicitly requested a small cinnabar carved seal bearing 纹 next to the top-left 纹启新生 title; preserve all other approved layout and color decisions. Do not return to masonry cards or monochrome beige surfaces.

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Refinement and workflow (2026-10-21)

The user rejected native blue OS dropdown menus and the modern-looking seal glyph. Use the shared ivory/ink-green/gold custom Select, including keyboard support, and the winding seal-script-style seal-wen-v2.png. Keep the approved equal project grid and restrained craft atmosphere. Composition, palette and export belong in the same local workspace, with persistent settings, actual downloads and clear unsaved/stale states. No deployment is requested.
