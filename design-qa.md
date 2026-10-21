# Design QA — 纹启新生本地创作工作台

final result: passed

## Visual truth and evidence

- Approved source: `C:/Users/Lenovo/.codex/generated_images/01a15c2e-5543-79e2-a049-93bf76efbc37/exec-58661bfa-fc9e-4dd9-81b8-f3a214266b7c.png`, 1024 × 1536. The user approved this refined atelier direction and then explicitly requested a small cinnabar 纹 seal next to the top-left brand, preserving the rest of the direction.
- Source crops saved as `docs/product/assets/2026-10-21/reference-library.png` and `reference-editor.png`. Original screen regions: library (14,84)–(1012,774), editor (14,792)–(1012,1489). Board heading and outer decoration excluded.
- Same-width comparison CSS viewport: 1000 × 690; devicePixelRatio reported 1.00000003. Source screen crops normalized to 1000 px wide. Full-page library screenshot excludes the browser scrollbar and is 984 × 768; scaled to 1000 px wide for comparison, with source padded below rather than stretched. Editor screenshot is 1000 × 690; source is 1000 × 696, a 6 px bottom difference retained. These are concept-to-implementation comparisons, not pixel-diff claims.
- Final full-view combined evidence: `docs/product/assets/2026-10-21/compare-library-v2.jpg`, `compare-editor-v2.jpg`.
- Focused combined brand evidence: `docs/product/assets/2026-10-21/compare-brand.jpg`. It shows the added seal beside the existing serif title and gold rule. Source has no seal; this is the explicitly requested delta.
- Additional rendered evidence: `web-library-desktop.png` (1440 × 900 CSS viewport, full-page raster 1424 × 968), `web-editor-1280.png` (1280 × 720 CSS), `web-library-mobile.png` and `web-editor-mobile.png` (390 × 844 CSS; full-page captures).
- Implementation URL: http://127.0.0.1:8510.

## State and intentional product adaptations

Library is an unfiltered six-item reference-material grid. Source concept uses fictional project names/dates and repeated detail crops; implementation uses the six repository source photographs with real catalog labels, and explicitly distinguishes examples from saved projects. No AI-generated specimen thumbnails were substituted for actual source photos.

Editor comparison is the original-image view with a rectangular selection, a removal brush mark, and keep tool active after saving. The concept shows an illustrative perfect flower cutout; implementation shows a real OpenCV result and its actual mask. This does not validate segmentation quality. The fitted image shows the original complete embroidery; zoom is available to examine a detail like the concept.

The implementation adds a preview action, download, and processing-settings disclosure because it is connected to the actual processing workflow. Inspector scrolls at short desktop heights, and stacks below the canvas on narrow screens. The small additional sidebar width accommodates the requested seal. No masonry layout, banner, promotional cards, or new color scheme was introduced.

## Comparison history and findings

1. Initial library comparison: `compare-library-v1.jpg`.
   - P2: The stacked subtitle and example-explanation row pushed the artwork below the reference's intended compact header. Fixed with an inline desktop subtitle and moving the explanation below the grid. `compare-library-v2.jpg` shows the restored top hierarchy and aligned card rows.
   - P2: Center crop removed the year-picture figure's face. Fixed its image focal point at 50% 12%. Final comparison visibly retains the face.
   - P2: Narrow-screen settings button lost its accessible name when its visible text was hidden. Added permanent aria-label; mobile DOM identifies 设置.
2. Initial editor screenshot was captured during viewport transition and included stale raster dimensions. Excluded from acceptance; recaptured after reading current DOM dimensions. `compare-editor-v2.jpg` contains the stabilized editor.
3. Final combined comparisons and focused brand crop were opened and inspected. No remaining actionable P0/P1/P2 visual findings for this slice. Responsive DOM checks at 1280 and 390 px showed no horizontal document overflow.

## Required fidelity surfaces

- Typography: local Noto Serif SC display/title text with Noto Sans SC controls. Clear display/body contrast, serif project names, readable small metadata, no broken title wrap. Library and editor brand use the same seal asset and serif family. Longer real project names truncate in a predictable single line.
- Layout rhythm: equal-size three-column desktop cards, shared baselines and consistent gaps; two columns on narrow screens. Ink navigation, compact title/search row, flat category tabs, minimal card chrome. Editor retains left assets / central canvas / right tools anatomy.
- Color tokens: ink green #23483d, warm ivory #faf9f4, pale celadon #e9eee4, restrained gold #b29b5a, red seal. Hover/focus/selected/disabled states remain distinct. No decorative gradients.
- Image fidelity: original catalog photographs with their material texture, verified raster botanical ornament, transparent raster seal. Seal remains legible at its 29–34 px UI size. Phosphor provides standard UI icons; no decorative SVG or CSS art substitutes. Year-picture focal point corrected.
- Copy: natural standalone Chinese labels; actual dates and saved states; examples clearly distinguished. Provenance disclosure retains source, creator and license. No concept-board headings or implementation instructions appear in the product.
- Accessibility: controls labelled, dialog role and keyboard focus trap, focus restoration, Escape close, keyboard undo/redo/save, range input names, reduced-motion styling. Full keyboard-only drawing is outside the current canvas scope; other controls remain keyboard reachable.

## Functional verification

- Browser: open example → rectangle selection → remove stroke → undo → redo → edge softening → real preview → save → download PNG → reopen with saved controls. Download completed to the browser's Downloads folder.
- Browser: rename and archive practice project, name search and category filter (one expected match each), open new-project dialog, choose a local image, create and open uploaded project. Verification projects were archived afterwards; original source assets were not modified.
- Browser: desktop, compact desktop and narrow-screen layout inspected. Console warn/error query returned no entries.
- Automated: 495 Python tests passed, including 10 new local API tests; 6 Node tests passed (editor state/coordinate behavior plus protected build packaging). Vite production build passed. git diff --check passed.
- Existing test infrastructure emits one upstream Starlette/httpx deprecation warning; it did not affect behavior.

## Implementation checklist

- [x] Add requested 纹 seal to both brand placements.
- [x] Preserve approved orderly grid, palette and editor anatomy.
- [x] Connect actual project persistence and extraction.
- [x] Check original source bytes and source alpha preservation.
- [x] Verify local API boundaries and revision conflicts.
- [x] Capture source and implementation together, fix P2s and recapture.
- [x] Keep local preview available; no public deployment.

## Follow-up polish and limits

Historical slice limitation (superseded by the local-completion section below): the first delivery did not yet include drafts, versions, duplication, recomposition or generation migration. Complex embroidery still requires visual checks and brush correction. Cloud hosting remains out of scope.


## 2026-10-21 refinement: menus, seal, composition, palette and export

Final result: passed for this requested local-workspace slice. No deployment.

Visual reference remains the approved atelier board and the user's two latest screenshots. Requested deltas: replace OS-native blue menus and the modern-looking seal glyph; extend the existing editor into composition/palette/export without redesigning the library. The new generated seal uses winding, even-width seal-script-style strokes; it is decorative design, not an authenticated historical glyph.

Evidence in `docs/product/assets/2026-10-21/`:
- `menus-v2.png`: ivory menu, restrained gold border, ink-green selected row, new seal and unchanged library geometry (1440 × 900 CSS viewport).
- `menus-mobile-v2.png`: 390 × 844 CSS viewport; measured popup left 168, right 378, bottom 555.33, within the viewport; Escape closes without selecting.
- `composition-desktop-v2.png`: new layout inspector using the existing celadon rail, dark central canvas and ivory controls. Initial QA found the preview action below the fold; fixed with a separate pinned action area. See final `composition-desktop-final.png` at 1280 × 720.
- `composition-mobile-v2.png` and `export-mobile-v2.png`: controls stack below the canvas at 390 × 844; document scroll width 375 ≤ viewport 390, no horizontal overflow.
- `palette-desktop-final.png`: saved six-color substitutions restored after page reload and reopening.
- `compare-menus-v2.jpg`: user screenshot beside implemented menu; this is a visual comparison across different viewport sizes/project counts, not a pixel-diff assertion.

The integration fixture uses the repository's actual photographed red paper-cut strip (the legacy demo is named lotus-paper-cut). Its uncorrected OpenCV mask retains considerable noise/background. These screenshots validate UI and file/state consistency, **not extraction quality**; manual correction remains necessary. No generated perfect specimen was substituted to conceal this limitation.

Browser workflow: created a separate local QA project from the bundled photo; saved extraction; opened composition; chose four-way repeat, blue/white palette, solid ivory background; previewed and saved 1024 × 1024; generated and actually downloaded PNG, ZIP and SVG; refreshed and reopened; confirmed layout, palette, background and historical export links persisted. The QA project is archived after verification. User's existing embroidery project was not edited.

Downloaded PNG bytes match the saved composition exactly. ZIP was opened and its design settings/source SHA checked against the project, and it excluded the original when unchecked. SVG was parsed as valid XML with an SVG root. Tests also verify stale revisions, all six layouts, exact preview/export pixels at small sizes, source-byte preservation, texture/alpha-preserving recolor, ZIP source opt-in, SVG failure, and current-result invalidation while historical downloads remain immutable.

Verification: 504 Python tests passed (one upstream Starlette/httpx deprecation warning); six Node tests passed; production build and Sites packaging passed; no deployment tool invoked. Final React review removed a circular Editor/Workspace import by extracting Stages; no runtime library added. Select keyboard selection and Escape were exercised in the browser; popup is portaled to avoid clipping and retains trigger focus. No remaining actionable P0/P1/P2 UI findings for this slice.


## 2026-10-21 local feature completion

Scope: complete the agreed single-process local personal workspace, without deployment. Added draft autosave/recovery, named versions and comparison/restore, full backup/import/duplication and damaged-record recovery, extraction choices, composition/palette history, creative generation/settings/jobs, mockups, local install/upgrade/diagnostics and user documentation.

Browser evidence:
- Created an isolated QA project from the actual repository paper-cut photograph. Changed feather to 1; observed autosave; reopened in Edge and recovered the server-side draft with the value intact. Editing is disabled until pending recovery is resolved.
- Saved extraction, changed composition, exercised undo/redo, applied the blue/white palette, saved a named design, compared two versions and restored the named version through the styled confirmation dialog. A before-restore snapshot remains available.
- Created an actual bookmark mockup, viewed analysis without losing the artwork, and downloaded a real PNG plus the complete project backup. The downloaded backup was imported and duplicated in an isolated API test workspace, with artwork, mockup, original bytes and historical exports intact.
- Full real-project duplication initially exposed a transient core mockup lock in the ZIP. Fixed new backups to omit recognized runtime locks and old imports to discard only exact-signature, indexed locks. Arbitrary lock files remain rejected. Repeated the actual browser duplicate operation successfully.
- Edge file-chooser automation was unavailable because its extension lacks local-file access; no permission was changed. The import UI was inspected, while the downloaded archive itself and multipart import were verified through the actual API. This is not a claim of completed browser file-upload automation.
- The in-app browser native confirm blocked its automation session. Replaced application confirmations with matching React dialogs, then completed browser verification in Edge. No paid generation was sent; provider success, failure, idempotency, cancellation, conflict and credentials were exercised with simulated adapters.
- Settings display available local capabilities, missing MobileSAM dependency/weights, session-key controls, recovery inspection and local help. No API key entered.
- Final desktop viewport 1440x900; narrow viewport 390x844, document width 375px (no horizontal overflow). Temporary viewport override reset. QA projects archived; the existing embroidery project was not modified.

Images in docs/product/assets/2026-10-21:
- versions-local-complete.png: named and automatic versions, two-way comparison.
- creative-complete-desktop.png and creative-complete-mobile.png: initial workflow evidence, before real-photo extraction correction; not final quality examples.
- creative-complete-desktop-final.png and creative-complete-mobile-final.png: actual cropped paper motif, saved blue/white repeat and bookmark mockup after extraction improvement.
- settings-complete-mobile.png: service settings/capabilities/recovery UI.

Extraction evidence: the real 2048px photo initially fell back to fragmented edges because dark reddish wood shared the paper hue. A guarded brightness-split retry now retains 99.92% of the independently selected obvious-red core and excludes the tested top-wall/bottom-wood anchor regions. Tests also cover low-light artwork and reject uniform/low-contrast backgrounds. These are partial quality anchors, not a full ground-truth mask or a promise of perfect segmentation on arbitrary photographs. Final browser flow also selected a single paper strip and preserved its cutouts.

Independent review fixes: analysis uses an isolated snapshot and preserves downstream artwork; active generation blocks project mutations/export; failed after-save snapshots report the successful saved revision plus a warning; unresolved drafts cannot silently accept unsaved edits; MobileSAM capability checks agree across settings/editor. No unresolved actionable findings from this review remain.

Local delivery verification: installation check, redacted diagnostics, source bundle manifest/hash verification, side-by-side upgrade preserving old/private data, and isolated backend startup were exercised on this machine. This is a Python 3.11 source bundle with built frontend, not a standalone executable or clean-Windows-machine certification. No deployment performed.

Final checks: 607 Python tests passed (one upstream Starlette/httpx deprecation warning); six Node tests passed; production build, dependency check and local installation check passed. After the final package allowlist adjustment, all nine local-release tests passed again.
