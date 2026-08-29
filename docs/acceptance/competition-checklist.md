# Competition acceptance checklist

Dated evidence for Pattern Reborn MVP. Headed Streamlit was not left running. Live paid credentials were not loaded or recorded.

1. Clean Windows bootstrap and drive-local cache inspection. **Date: 2026-08-30.** `scripts\bootstrap.ps1` and `scripts\run.ps1` set `PIP_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME`, `TEMP`, and `TMP` under the repository `.cache\` tree. Smoke start used `.\.venv\Scripts\python.exe -m streamlit` with `--server.address=127.0.0.1`. Cache directories `.cache\pip`, `.cache\huggingface`, `.cache\torch`, `.cache\xdg`, and `.cache\tmp` exist on the worktree drive. No global `pip` was used.

2. Full offline fixture pipeline. **Date: 2026-08-30.** `tests/integration/test_offline_pipeline.py::test_offline_pipeline_reaches_export_without_generation` covers create → extract → confirm → analyze → compose → mockup → export without generation. `.\scripts\test.ps1 -q` → **265 passed** in 34.22s. Coverage `85.27%` with `--cov-fail-under=85`.

3. Six demo projects when assets are supplied. **Date: 2026-08-30.** `data/demo/manifest.json` lists `lotus-paper-cut`, `fish-lotus-blue-calico`, `peony-embroidery`, `scrolling-lotus-ceramic`, `new-year-picture-detail`, `architectural-cloud`. Confirmed with `.\.venv\Scripts\python.exe scripts\validate_demo_assets.py data/demo --competition-ready`.

4. Manual Seedream/Qwen switching with mocked and authorized live tests. **Date: 2026-08-30.** UI tests in `tests/ui/test_generation_controls.py` assert both providers, platform/BYOK modes, and no automatic provider switch. Adapter tests use respx fakes only. **Live paid API skipped** in this agent session (no credential inspection, zero live calls).

5. API outage / cached-result presentation. **Date: 2026-08-30.** `test_cached_generated_assets_remain_exportable_offline` keeps previously downloaded generation files exportable after the fake adapter is set to fail. Cached outputs remain `ai_assisted`.

6. BYOK key absence from repository search and exports. **Date: 2026-08-30.** `.gitignore` excludes `.env`. Exporter redacts secret-shaped strings to `[REDACTED]`. Automated `git grep` secret scan: no live credentials; test fixture `sk-secret-value` / redaction regex `sk-` are false positives (see Task 16 report).

7. Canvas absent fallback. **Date: 2026-08-30.** Smoke test sets `PATTERN_REBORN_DISABLE_OPTIONAL=1` and still receives HTTP 200 from `/_stcore/health`. Studio copy: `未检测到可绘制画布组件，已回退为框选与提示点输入。` Numeric box and point inputs remain when `streamlit_drawable_konva` is missing.

8. MobileSAM absent fallback. **Date: 2026-08-30.** `tests/test_capabilities.py` asserts missing MobileSAM reports Chinese reason while OpenCV segmentation still produces a mask. Core install does not import Torch at capability probe.

9. SVG unavailable fallback. **Date: 2026-08-30.** Capability probe treats missing VTracer independently; PNG mockup/export continue. Chinese reason: `未检测到 VTracer，已禁用 SVG 导出。PNG 工作流不受影响。`

10. Source / license / AI labels in generated report. **Date: 2026-08-30.** Export writes `provenance.md`, `attribution.md`, and `manifest.json` with provenance class, SHA-256, and `ai_assisted` on generation files. Tests in `tests/test_exporter.py` cover labels and redaction.

## Notes

- Headed `.\scripts\run.ps1 --server.headless false --server.port 8501` was not used; smoke helper bound `127.0.0.1`, polled health, then terminate/wait/kill of that child only.
- Date is the agent run date (2026-08-30), not a backfilled 2026-08-29 log.
