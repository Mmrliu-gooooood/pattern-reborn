# Third-party notices

Columns: **Name**, **Purpose**, **License**, **Copyright owner**, **Upstream URL**, **Redistributed** in this Git tree, **Notice action**.

Python wheels live only in gitignored `.venv\` unless noted. Demo JPEGs in `data/demo/` **are** redistributed; keep their license terms.

| Name | Purpose | License | Copyright owner | Upstream URL | Redistributed | Notice action |
|---|---|---|---|---|---|---|
| streamlit | Local browser UI | Apache-2.0 | Snowflake Inc. | https://github.com/streamlit/streamlit | No (venv) | Preserve Apache-2.0 notice; not claimed as original work |
| pydantic | Typed records and config | MIT | Samuel Colvin and Pydantic contributors | https://github.com/pydantic/pydantic | No (venv) | Preserve MIT copyright |
| opencv-python-headless | Deterministic image processing | Apache-2.0 | OpenCV Team | https://github.com/opencv/opencv-python | No (venv) | Preserve Apache-2.0; OpenCV is an engine, not team IP |
| Pillow | Image I/O | MIT-CMU (PIL/Pillow) | Jeffrey A. Clark and contributors | https://github.com/python-pillow/Pillow | No (venv) | Preserve PIL/Pillow copyright |
| numpy | Array math | BSD-3-Clause (and bundled notices) | NumPy developers | https://numpy.org | No (venv) | Preserve BSD notices |
| httpx | HTTPS client for providers | BSD-3-Clause | Encode / Tom Christie | https://github.com/encode/httpx | No (venv) | Preserve BSD notice |
| python-dotenv | Load untracked `.env` | BSD-3-Clause | Saurabh Kumar | https://github.com/theskumar/python-dotenv | No (venv) | Preserve BSD notice |
| vtracer | Optional raster-to-SVG | MIT | Chris Tsang / visioncortex | https://www.visioncortex.org/vtracer | No (venv) | Preserve MIT; SVG export is optional |
| pytest | Test runner (dev) | MIT | Holger Krekel and pytest contributors | https://github.com/pytest-dev/pytest | No (venv) | Dev-only; preserve MIT |
| pytest-cov | Coverage (dev) | MIT | pytest-cov contributors | https://github.com/pytest-dev/pytest-cov | No (venv) | Dev-only; preserve MIT |
| respx | Fake HTTP for adapter tests (dev) | BSD-3-Clause | Jonas Lundberg | https://github.com/lundberg/respx | No (venv) | Dev-only; preserve BSD |
| streamlit-drawable-konva | Optional studio canvas | Package license on PyPI (0.2.2) | Package authors | https://pypi.org/project/streamlit-drawable-konva/ | No (optional extra) | Install only via venv extra `canvas`; UI falls back if absent |
| MobileSAM | Optional guided segmentation | Apache-2.0 | Chaoning Zhang et al. | https://github.com/ChaoningZhang/MobileSAM | No (gitignored `models/`) | Install via `scripts\install_optional_ai.ps1`; checkpoint is not team-authored |
| PyTorch / torchvision | Optional MobileSAM runtime | BSD-style | PyTorch contributors | https://pytorch.org | No (venv) | CPU wheel by default; not required for OpenCV path |
| lotus-paper-cut source.jpg | Competition demo | CC BY-SA 4.0 | Sean Chiu | https://commons.wikimedia.org/wiki/File:%E5%AE%A2%E5%AE%B6%E4%BA%94%E7%A6%8F%E5%89%AA%E7%B4%99.jpg | Yes (`data/demo/`) | Attribute Sean Chiu; share-alike on adapted source |
| fish-lotus-blue-calico source.jpg | Competition demo | Public Domain | 上海博物馆 (scan on Commons) | https://commons.wikimedia.org/wiki/File:%E8%8B%8F%E5%B7%9E%E9%87%91%E9%B1%BC%E8%8D%B7%E8%8A%B1%E8%93%9D%E5%8D%B0%E8%8A%B1%E5%B8%83%E8%A2%AB%E9%9D%A2.jpg | Yes (`data/demo/`) | Keep public-domain label; not claimed as original |
| peony-embroidery source.jpg | Competition demo | CC0 / The Met Open Access | The Metropolitan Museum of Art, 1987.277 | https://www.metmuseum.org/art/collection/search/39735 | Yes (`data/demo/`) | Keep Met Open Access / CC0 notice |
| scrolling-lotus-ceramic source.jpg | Competition demo | CC BY-SA 4.0 | 三十三画生 | https://commons.wikimedia.org/wiki/File:%E9%9D%92%E8%8A%B1%E7%BC%A0%E6%9E%9D%E8%8E%B2%E7%BA%B9%E8%8F%B1%E8%8A%B1%E5%8F%A3%E7%9B%98%E7%BB%86%E9%83%A8.jpg | Yes (`data/demo/`) | Attribute photographer; share-alike |
| new-year-picture-detail source.jpg | Competition demo | Public Domain | Anonymous workshop; scan Alexey Parygin's Collection | https://commons.wikimedia.org/wiki/File:1900s_Nianhua_The_Spirit_of_the_Doors_woodblock_print.jpg | Yes (`data/demo/`) | Keep public-domain label |
| architectural-cloud source.jpg | Competition demo | CC BY-SA 3.0 | 秋水平湖 | https://commons.wikimedia.org/wiki/File:%E5%A4%AA%E5%92%8C%E6%AE%BF%E6%A9%AB%E6%A8%91%E7%9A%84%E9%87%91%E9%BE%8D%E5%92%8C%E7%92%BD%E5%BD%A9%E7%95%AB.JPG | Yes (`data/demo/`) | Attribute photographer; share-alike |
| assets/mockups/*.png | Neutral product templates | Project-original | Pattern Reborn team | in-repo `assets/mockups/` | Yes | Team-authored; cite as project-original in exports |
| src/.../ruyi_cloud.svg | Navigation ornament | Project-original | Pattern Reborn team | in-repo UI assets | Yes | Original paths; comment `Pattern Reborn original asset` |

Provider HTTP APIs (Volcengine Ark / Seedream, Alibaba Model Studio / Qwen Image) are remote services, not redistributed code. Model names and base URLs live in `config/providers.json`. Generated pixels are AI-assisted and must stay labeled in the UI, manifest, and provenance report.

This project does not describe third-party engines, public-domain scans, or API outputs as the team's original artwork.
