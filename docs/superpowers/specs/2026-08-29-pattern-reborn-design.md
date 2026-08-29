# Pattern Reborn Design Specification

**Chinese product name:** 纹启新生——非遗纹样智能提取与再设计平台  
**English product name:** Pattern Reborn  
**Repository:** `D:\code\ican\pattern-reborn`  
**Target platform:** Windows 10/11 x64  
**Specification date:** 2026-08-29

## 1. Purpose and success criteria

Pattern Reborn is a local-first, guided creation studio for digitizing and redesigning Chinese intangible-cultural-heritage and traditional patterns. It turns one source image into a traceable chain of results: extracted motif, visual analysis, parameterized repeat, optional API-generated derivative, cultural-product mockup, and an exportable provenance report.

The MVP succeeds when a user can run the application on the competition laptop and complete the following workflow without Docker, WSL, a database service, or globally installed project dependencies:

1. Create or reopen a local project.
2. Upload a supported image and record its source and license status.
3. Select one of nine craft categories and automatically receive one of four processing profiles.
4. Produce and manually correct a usable motif mask.
5. Inspect palette, traditional-color matches, contour metrics, and symmetry analysis.
6. Create at least one parameterized repeat pattern.
7. Optionally generate one creative derivative through Seedream or Qwen Image.
8. Place a selected result on a cultural-product mockup.
9. Export images, SVG when available, project metadata, and a provenance report.
10. Complete steps 1–6, 8, and 9 while offline; only API generation may be unavailable.

The competition demonstration must be stable with six prepared examples and must not depend on a successful live network request. Cached API results remain visibly labeled as AI-assisted outputs.

## 2. Scope

### 2.1 Supported content categories

The knowledge catalog and upload workflow support all nine categories:

1. Paper cutting.
2. Embroidery and brocade.
3. Blue calico, batik, and tie-dye.
4. Ceramic ornament.
5. Lacquer ornament.
6. New Year pictures and folk painting.
7. Architectural painting, brick carving, and wood carving.
8. Gold, silver, and jewelry ornament.
9. Kites, shadow puppets, and masks.

The software does not claim that every traditional image is an officially recognized intangible-cultural-heritage item. Each record has one of three provenance classifications: `verified_ich_source`, `traditional_reference`, or `user_supplied_unverified`.

### 2.2 Processing profiles

The nine categories map to four reusable profiles rather than nine separately trained pipelines:

- **Silhouette:** paper cutting, shadow puppets, and text-like motifs. Prioritizes binary separation, contour preservation, and hole retention.
- **Flat color:** New Year pictures, lacquer, kites, architectural painting, and other planar color motifs. Prioritizes color-region separation and controlled palette reduction.
- **Textile:** embroidery, brocade, blue calico, batik, and tie-dye. Prioritizes texture suppression, thread/detail preservation, and palette stability.
- **Artifact photograph:** ceramics, carving, jewelry, and masks. Prioritizes manual region selection, perspective assistance, highlight/shadow tolerance, and conservative extraction.

The artifact profile is assistive. It does not promise professional unwrapping of curved surfaces, removal of all reflections, or recovery of geometry hidden from the photograph.

### 2.3 Demonstration cases

The MVP ships with six traceable demo projects when suitable licensed or self-created source images are available:

1. Lotus paper cutting — contour extraction, mirror/radial composition.
2. Fish-and-lotus blue calico — two-color separation and seamless repeat.
3. Peony embroidery — texture suppression and traditional-color matching.
4. Blue-and-white scrolling lotus — box-guided extraction and blue-white preservation.
5. Detail from a New Year picture — complex color-region extraction and local redesign.
6. Architectural painting or carved cloud motif — contour enhancement, symmetry analysis, and API-assisted derivative.

Every bundled demo records the source, author or institution when known, license, retrieval date, processing defaults, expected result, and AI involvement. Search-engine images with unclear reuse rights are not bundled. Self-created or generated demonstration inputs are labeled as demonstration material rather than historical artifacts.

### 2.4 Explicit exclusions

The MVP does not include user accounts, cloud sync, collaboration, model training, a local Stable Diffusion production path, professional embroidery-machine output, full SVG node editing, mobile layout, or authoritative cultural authentication. It does not describe third-party models or public datasets as the team's original work.

## 3. Product flow and interface

### 3.1 Home page

The home page contains one primary “New Creation” action, the three most recent local projects, nine category shortcuts, six demo cases, a knowledge-catalog entry, settings, and clear local/API readiness indicators. Project history is intentionally lightweight; it is not a dashboard-centric product.

### 3.2 Guided six-step studio

The studio uses a persistent left navigation rail and one focused main work area:

1. **Upload and classify:** image, project name, craft category, motif subject, source, and rights status.
2. **Smart extraction:** preprocessing, automatic mask, point/box-guided refinement, keep/remove brushes, and mask confirmation.
3. **Pattern analysis:** dominant colors, traditional-color matches, contour complexity, symmetry axes, and rotational order candidates.
4. **Parameterized recomposition:** mirror, rotation, radial composition, border repeat, two-way repeat, and four-way repeat.
5. **AI creative generation:** provider mode, manually switchable Seedream/Qwen selection, prompt composition, confirmation, generation, and history.
6. **Export and provenance:** selected assets, cultural-product mockups, metadata manifest, component attribution, and provenance report.

Advanced algorithm controls are collapsed by default. Each step preserves user inputs and results when the user navigates backward or forward.

### 3.3 Visual language

The approved style is “rice paper and ink green with a vermilion seal and restrained gilding.”

- Warm paper white is the primary canvas.
- Ink green is the navigation color.
- Vermilion is reserved for the primary action and seal mark.
- Gold appears only in progress markers, thin dividers, small status details, and fine borders.
- The background has subtle non-directional tonal variation; it must not use ruled or diagonal line patterns.
- The navigation uses a low-opacity original ruyi-cloud line drawing and a small vertical “非遗纹启” seal.
- Image editing surfaces remain neutral so the application chrome does not distort color judgment.
- The application uses installed system Chinese fonts; it does not bundle fonts with unclear rights.
- Decorative imagery is implemented as original SVG/CSS assets, not copied photographs.

## 4. Architecture

### 4.1 Technology choices

- Python 3.11.
- Streamlit for the local browser interface.
- OpenCV, Pillow, and NumPy for deterministic image processing.
- MobileSAM for optional click/box-guided segmentation.
- VTracer for raster-to-SVG conversion.
- HTTP adapters for Seedream and Qwen Image.
- JSON files and ordinary directories for persistence.
- Pytest for unit, integration, and image-contract tests.

Streamlit contains no image-processing logic. The UI calls workflow services, which call focused domain modules. This permits later migration to a different frontend without rewriting the processing core.

### 4.2 Components

- **Project repository:** creates, validates, lists, loads, and atomically saves local projects.
- **Knowledge catalog:** reads curated craft, subject, cultural-note, source, and license records.
- **Profile resolver:** maps category selection to one processing profile and explicit default parameters.
- **Preprocessor:** orientation correction, safe resizing, crop, perspective transform, denoise, white balance, and contrast adjustment.
- **Segmentation service:** OpenCV baseline masks plus an optional MobileSAM implementation behind a common interface.
- **Mask editor model:** applies keep/remove strokes and records edits without mutating the original source image.
- **Analyzer:** palette extraction, traditional-color matching, contour metrics, bilateral symmetry scores, and rotational-symmetry candidates.
- **Pattern composer:** deterministic transforms and repeat generation driven by a stored random seed and parameters.
- **Vectorizer:** converts a confirmed extracted result to SVG through VTracer and reports capability availability.
- **Generation service:** validates a provider-neutral request and delegates to a selected API adapter.
- **Mockup composer:** places motifs on locally bundled, rights-cleared product templates.
- **Exporter:** produces selected images, SVG, JSON manifest, attribution, and a human-readable provenance report.

### 4.3 Data flow

The immutable source image is copied into the project, hashed, and never overwritten. Processing creates a bounded working copy for interactive operations. Each confirmed step writes a new versioned artifact and updates `project.json` atomically. Downstream steps consume confirmed artifacts; changing an upstream confirmation marks dependent outputs stale rather than silently presenting them as current.

## 5. Local persistence

Each creation project is stored under `workspace/<project_id>/`:

```text
workspace/<project_id>/
├── project.json
├── source/
├── masks/
├── extracted/
├── patterns/
├── generated/
├── mockups/
└── exports/
```

`project.json` stores the project name, timestamps, category, subject, provenance classification, source hash, confirmed-step state, processing profile and parameters, artifact paths, palette, symmetry analysis, repeat parameters and seed, API provider/model/prompt/timestamp, manual-edit records, AI labels, and third-party attribution references.

Writes use a temporary sibling file followed by an atomic replace. A corrupt or unsupported project version is reported without overwriting the original file.

## 6. API generation

### 6.1 Modes

- **Platform default:** credentials are read from the competition laptop's untracked `.env`. The user does not see the secret.
- **Bring your own key (BYOK):** the user selects a provider and enters a key for the current Streamlit session. The key is held only in memory and is not written to projects, reports, logs, browser storage, or error messages.

Platform-default credentials are suitable only for the controlled competition laptop. They are not embedded into a distributable application. A future public deployment would require a server-side credential proxy, authentication, quotas, and abuse controls; those are outside the MVP.

### 6.2 Providers and manual selection

Seedream and Qwen Image are both visible choices in step 5 for both credential modes. Seedream is initially selected, and Qwen Image 3.0 Pro is the secondary default; “default” does not hide or lock the choice. Switching providers preserves the prompt, reference motif, color constraints, structure-preservation level, target product, and requested size.

The application never automatically retries on a different paid provider. The user explicitly chooses whether to retry or switch, preventing accidental duplicate charges.

Provider model identifiers, regional base URLs, and optional endpoint IDs are configuration values rather than source-code constants. The initial presets target the models available to the competition accounts at setup time.

### 6.3 Provider-neutral request

A generation request contains:

- Prompt and one extracted reference image.
- Provider and model identifier.
- Credential mode.
- Output size and exactly one requested image in the MVP.
- Structure-preservation level: low, medium, or high.
- Target application such as packaging, bookmark, textile, poster, or phone case.
- Selected traditional colors and negative constraints.

Before dispatch, the UI displays provider, model, size, and image count. Results returned as temporary URLs are downloaded immediately; base64 results are decoded locally. The raw result is preserved, while the UI, mockups, and reports visibly mark it as AI-assisted. The request metadata never includes the credential.

## 7. Error handling and capability degradation

- Unsupported or malformed images produce a Chinese explanation and supported-format list.
- Oversized images retain the original and create a bounded working copy.
- Failed automatic segmentation offers box/point selection and the OpenCV/manual path.
- Missing MobileSAM disables guided AI segmentation without disabling the rest of the studio.
- Missing VTracer disables SVG only; PNG export remains available.
- API authentication, quota, moderation, timeout, and malformed-response errors map to user-readable messages with a redacted provider code.
- Generation settings and prompt survive failed calls.
- Temporary result URLs are downloaded before a generation is marked successful.
- Upstream changes mark later artifacts stale and explain what must be regenerated.
- Missing demo assets hide that demo card and report the missing local file rather than failing application startup.

## 8. Isolation and reproducibility

All mutable project dependencies and caches live beneath `D:\code\ican\pattern-reborn`:

```text
pattern-reborn/
├── .venv/
├── .cache/
│   ├── pip/
│   ├── huggingface/
│   └── torch/
├── models/
├── workspace/
└── outputs/
```

Startup scripts set `PIP_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME`, and model-specific cache variables to these local paths before invoking Python. Dependencies are installed only with the project virtual environment's Python executable. The workflow does not alter system `PATH`, install global Python or Node packages, write secrets into source files, or require Docker, WSL, a database service, or a globally installed CUDA toolkit.

## 9. Testing and acceptance

Development follows test-driven development for product behavior.

- Unit tests cover profile resolution, color matching, symmetry scoring, repeat transforms, validation, paths, and configuration redaction.
- Image-contract tests use small fixed fixtures and assert dimensions, alpha channels, mask bounds, deterministic seeds, and non-mutation of source files.
- Repository tests cover creation, atomic save, reload, schema validation, stale-output propagation, corrupt JSON, and project-history ordering.
- API adapter tests use local fake HTTP responses that mirror complete documented response structures; tests never spend API credits.
- Integration tests execute the local pipeline from fixture input through extraction, analysis, repeat, mockup, and export.
- A Windows smoke test starts the application using the project launcher from a clean PowerShell process.
- Manual acceptance runs all six prepared demo cases through the six-step workflow.
- Offline acceptance confirms that all features except step-5 API generation remain usable.
- Demonstration acceptance confirms that cached API results and a live-generation control coexist, so a network outage cannot block the presentation.

## 10. Attribution and competition compliance

The repository retains required license notices for OpenCV, MobileSAM, VTracer, datasets, templates, and any other redistributed asset. The application and report distinguish team-authored workflow and algorithms from third-party engines. AI-generated or AI-assisted output is labeled in the interface, exported manifest, and presentation material. Development logs record real work chronologically; they are not backfilled with fabricated activities. Blind-review exports omit institution and instructor names.
