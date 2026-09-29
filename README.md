# Static site engine

Static site generator and publishing workflows.

- `frontend/` — static pages and data files.
- `tools/` — site build scripts.
- `promotion/` — outreach and analytics scripts.
- `aggregator/` — content ingest.
- `.github/workflows/` — scheduled jobs, QA and deployment.

Build locally:

```bash
python3 tools/build_seo.py
cd frontend && python3 -m http.server 8080
```
