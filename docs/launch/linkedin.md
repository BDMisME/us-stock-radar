# LinkedIn post draft (English, professional)

> Usage: copy the body to LinkedIn. Attach 1–2 screenshots from `docs/img/` (portfolio.png + kline.png work well). Swap the repo link for the final public URL before posting.

---

📡 I open-sourced **us-stock-radar** — a personal US-stock monitoring dashboard with a resident AI analyst. MIT-licensed.

The problem: I can't watch the market all day, but I don't want to miss the moments that actually matter on my holdings — an MA break, a volume spike, price entering a buy zone I defined.

So I built a tool around one principle: **compress before you reason.** A rules engine turns raw ticks into ~15 discrete events; only those events reach the LLM. The model never reads per-second data — which keeps token cost and noise low, and makes the AI output (structured JSON: recommendation, action, risk, invalidation condition) genuinely useful.

A few engineering choices I'm happy with:

🔹 **SQLite (WAL) as the event queue.** Five resident processes — market monitor, signal engine, AI worker, alert worker, scheduler — coordinate purely through `signals` / `alerts` status columns. No Redis, no Kafka. Right-sized for a single-user workload.

🔹 **Graceful degradation everywhere.** Every API key (Alpaca, ARK, Finnhub, FMP, Telegram) is optional; missing keys fall back or mark `skipped` instead of crashing.

🔹 **Swappable data layer.** Sources implement a small `QuoteAdapter` / `HistoryAdapter` interface, so upgrading from free IEX to a paid full-market SIP feed is one adapter — nothing downstream changes.

🔹 **Tiered AI cooldown** (swing 2h / long-term 4h) so analysis stays signal, not spam.

Stack: Python · Streamlit · Plotly · SQLite · Volcengine ARK (OpenAI-compatible).

Important: this is **research tooling only** — no order placement, no broker trading API, no profit guarantees. The AI produces risk-aware research, not investment advice.

Code, docs, and a clean self-host path here 👇
🔗 https://github.com/BDMisME/us-stock-radar

Feedback and PRs welcome. (Self-hosting note: single-user by design, no auth — use your own keys and don't expose your live instance publicly.)

#OpenSource #Python #Streamlit #FinTech #AI #SoftwareEngineering #SideProject
