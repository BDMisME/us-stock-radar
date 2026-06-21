# Contributing to us-stock-radar

Thanks for your interest! This is a personal-scale, single-user tool — contributions that keep it simple and dependency-light are most welcome.

## Dev setup

```bash
python3.12 -m venv .venv          # 3.11+ required (macOS system 3.9 is too old)
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # all keys optional; blank still runs the demo

python scripts/init_db.py
python scripts/seed_demo.py
python scripts/backfill.py
streamlit run app/main.py
```

## Before opening a PR

- [ ] `pytest` is green.
- [ ] No secrets, API keys, or personal data committed (keys belong in `.env`, which is gitignored).
- [ ] New quote/history/news sources implement the interfaces in `data_adapters/base.py`.
- [ ] UI follows the existing dark, data-dense theme and the **Taiwan color convention (🔴 up / 🟢 down)**.

## Hard rules (non-negotiable, by design)

- **No order placement, no broker trading API, no scraping of broker apps.** This project is research-only.
- The AI must never claim guaranteed profit; it produces research and risk reminders only, and must state invalidation conditions.
- The LLM never reads raw per-second ticks — the rules engine (`signal_engine`) compresses events first.

## Scope

v1 serves a single personal user. Multi-user, auth, and SaaS features are intentionally out of scope.
