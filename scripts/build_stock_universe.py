"""Build config/stock_universe.json — a static list of ~600+ symbols with names.

Run once (or whenever you want to refresh the list):
    python scripts/build_stock_universe.py

Sources (in order, merged with dedup):
  1. S&P 500 from Wikipedia
  2. NASDAQ 100 from Wikipedia
  3. A curated list of popular / frequently-traded names

Output: config/stock_universe.json  — list of {"symbol": "AAPL", "name": "Apple Inc."}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT = PROJECT_ROOT / "config" / "stock_universe.json"

# ── Curated additions (symbols that matter to retail investors) ──────────────
EXTRA: list[tuple[str, str]] = [
    ("AAPL",  "Apple Inc."),
    ("MSFT",  "Microsoft Corporation"),
    ("GOOGL", "Alphabet Inc. Class A"),
    ("GOOG",  "Alphabet Inc. Class C"),
    ("AMZN",  "Amazon.com Inc."),
    ("META",  "Meta Platforms Inc."),
    ("TSLA",  "Tesla Inc."),
    ("NVDA",  "NVIDIA Corporation"),
    ("AMD",   "Advanced Micro Devices Inc."),
    ("INTC",  "Intel Corporation"),
    ("AVGO",  "Broadcom Inc."),
    ("QCOM",  "Qualcomm Inc."),
    ("TXN",   "Texas Instruments Inc."),
    ("MU",    "Micron Technology Inc."),
    ("AMAT",  "Applied Materials Inc."),
    ("LRCX",  "Lam Research Corporation"),
    ("KLAC",  "KLA Corporation"),
    ("ASML",  "ASML Holding NV"),
    ("TSM",   "Taiwan Semiconductor Manufacturing"),
    ("SMCI",  "Super Micro Computer Inc."),
    ("ARM",   "Arm Holdings plc"),
    ("PLTR",  "Palantir Technologies Inc."),
    ("SNOW",  "Snowflake Inc."),
    ("DDOG",  "Datadog Inc."),
    ("NET",   "Cloudflare Inc."),
    ("CRM",   "Salesforce Inc."),
    ("NOW",   "ServiceNow Inc."),
    ("ADBE",  "Adobe Inc."),
    ("ORCL",  "Oracle Corporation"),
    ("SAP",   "SAP SE"),
    ("UBER",  "Uber Technologies Inc."),
    ("LYFT",  "Lyft Inc."),
    ("ABNB",  "Airbnb Inc."),
    ("BKNG",  "Booking Holdings Inc."),
    ("EXPE",  "Expedia Group Inc."),
    ("NFLX",  "Netflix Inc."),
    ("DIS",   "The Walt Disney Company"),
    ("CMCSA", "Comcast Corporation"),
    ("T",     "AT&T Inc."),
    ("VZ",    "Verizon Communications Inc."),
    ("TMUS",  "T-Mobile US Inc."),
    ("JPM",   "JPMorgan Chase & Co."),
    ("BAC",   "Bank of America Corporation"),
    ("WFC",   "Wells Fargo & Company"),
    ("GS",    "Goldman Sachs Group Inc."),
    ("MS",    "Morgan Stanley"),
    ("C",     "Citigroup Inc."),
    ("BLK",   "BlackRock Inc."),
    ("SCHW",  "Charles Schwab Corporation"),
    ("AXP",   "American Express Company"),
    ("V",     "Visa Inc."),
    ("MA",    "Mastercard Inc."),
    ("PYPL",  "PayPal Holdings Inc."),
    ("SQ",    "Block Inc."),
    ("COIN",  "Coinbase Global Inc."),
    ("MSTR",  "MicroStrategy Inc."),
    ("BRK.B", "Berkshire Hathaway Inc. Class B"),
    ("UNH",   "UnitedHealth Group Inc."),
    ("JNJ",   "Johnson & Johnson"),
    ("PFE",   "Pfizer Inc."),
    ("MRNA",  "Moderna Inc."),
    ("ABBV",  "AbbVie Inc."),
    ("LLY",   "Eli Lilly and Company"),
    ("BMY",   "Bristol-Myers Squibb Company"),
    ("MRK",   "Merck & Co. Inc."),
    ("AMGN",  "Amgen Inc."),
    ("GILD",  "Gilead Sciences Inc."),
    ("BIIB",  "Biogen Inc."),
    ("REGN",  "Regeneron Pharmaceuticals Inc."),
    ("ISRG",  "Intuitive Surgical Inc."),
    ("MDT",   "Medtronic plc"),
    ("ABT",   "Abbott Laboratories"),
    ("TMO",   "Thermo Fisher Scientific Inc."),
    ("DHR",   "Danaher Corporation"),
    ("XOM",   "Exxon Mobil Corporation"),
    ("CVX",   "Chevron Corporation"),
    ("COP",   "ConocoPhillips"),
    ("SLB",   "Schlumberger Limited"),
    ("OXY",   "Occidental Petroleum Corporation"),
    ("NEE",   "NextEra Energy Inc."),
    ("D",     "Dominion Energy Inc."),
    ("WM",    "Waste Management Inc."),
    ("AMT",   "American Tower Corporation"),
    ("PLD",   "Prologis Inc."),
    ("EQIX",  "Equinix Inc."),
    ("SPG",   "Simon Property Group Inc."),
    ("HD",    "The Home Depot Inc."),
    ("LOW",   "Lowe's Companies Inc."),
    ("TGT",   "Target Corporation"),
    ("WMT",   "Walmart Inc."),
    ("COST",  "Costco Wholesale Corporation"),
    ("AMZN",  "Amazon.com Inc."),
    ("MCD",   "McDonald's Corporation"),
    ("SBUX",  "Starbucks Corporation"),
    ("NKE",   "Nike Inc."),
    ("LVS",   "Las Vegas Sands Corporation"),
    ("BA",    "The Boeing Company"),
    ("LMT",   "Lockheed Martin Corporation"),
    ("RTX",   "RTX Corporation"),
    ("NOC",   "Northrop Grumman Corporation"),
    ("GE",    "GE Aerospace"),
    ("CAT",   "Caterpillar Inc."),
    ("DE",    "Deere & Company"),
    ("MMM",   "3M Company"),
    ("HON",   "Honeywell International Inc."),
    ("EMR",   "Emerson Electric Co."),
    ("ETN",   "Eaton Corporation plc"),
    ("F",     "Ford Motor Company"),
    ("GM",    "General Motors Company"),
    ("RIVN",  "Rivian Automotive Inc."),
    ("LCID",  "Lucid Group Inc."),
    ("NIO",   "NIO Inc."),
    ("LI",    "Li Auto Inc."),
    ("XPEV",  "XPeng Inc."),
    ("BYD",   "BYD Company Limited"),
    ("BABA",  "Alibaba Group Holding Limited"),
    ("JD",    "JD.com Inc."),
    ("PDD",   "PDD Holdings Inc."),
    ("BIDU",  "Baidu Inc."),
    ("TCOM",  "Trip.com Group Limited"),
    ("SE",    "Sea Limited"),
    ("GRAB",  "Grab Holdings Limited"),
    ("SHOP",  "Shopify Inc."),
    ("MELI",  "MercadoLibre Inc."),
    ("NU",    "Nu Holdings Ltd."),
    ("PTON",  "Peloton Interactive Inc."),
    ("ROKU",  "Roku Inc."),
    ("SPOT",  "Spotify Technology SA"),
    ("RBLX",  "Roblox Corporation"),
    ("U",     "Unity Software Inc."),
    ("HOOD",  "Robinhood Markets Inc."),
    ("SOFI",  "SoFi Technologies Inc."),
    ("AFRM",  "Affirm Holdings Inc."),
    ("UPST",  "Upstart Holdings Inc."),
    ("BNPL",  "Sezzle Inc."),
    ("AI",    "C3.ai Inc."),
    ("PATH",  "UiPath Inc."),
    ("BBAI",  "BigBear.ai Holdings Inc."),
    ("SOUN",  "SoundHound AI Inc."),
    ("IONQ",  "IonQ Inc."),
    ("RGTI",  "Rigetti Computing Inc."),
    ("QUBT",  "Quantum Computing Inc."),
    ("KULR",  "KULR Technology Group Inc."),
    ("SMCI",  "Super Micro Computer Inc."),
    ("GLD",   "SPDR Gold Shares ETF"),
    ("SLV",   "iShares Silver Trust ETF"),
    ("GDX",   "VanEck Gold Miners ETF"),
    ("SPY",   "SPDR S&P 500 ETF Trust"),
    ("QQQ",   "Invesco QQQ Trust ETF"),
    ("IWM",   "iShares Russell 2000 ETF"),
    ("DIA",   "SPDR Dow Jones Industrial Average ETF"),
    ("TLT",   "iShares 20+ Year Treasury Bond ETF"),
    ("HYG",   "iShares iBoxx High Yield Corporate Bond ETF"),
    ("VIX",   "CBOE Volatility Index"),
    ("SQQQ",  "ProShares UltraPro Short QQQ ETF"),
    ("TQQQ",  "ProShares UltraPro QQQ ETF"),
    ("SOXL",  "Direxion Daily Semiconductors Bull 3X ETF"),
    ("SOXS",  "Direxion Daily Semiconductors Bear 3X ETF"),
]


def _http_get(url: str, timeout: int = 25) -> str:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def _fetch_sp500_datahub() -> list[tuple[str, str]]:
    """S&P 500 constituents from the datahub mirror (reliable, no 403)."""
    import csv
    import io
    url = ("https://raw.githubusercontent.com/datasets/"
           "s-and-p-500-companies/main/data/constituents.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(_http_get(url))))
    except Exception as e:
        print(f"[WARN] S&P 500 fetch failed: {e}")
        return []
    out = []
    for r in rows:
        sym = (r.get("Symbol") or "").strip().upper().replace(".", "-")
        name = (r.get("Security") or "").strip()
        if sym and name:
            out.append((sym, name))
    return out


_NAME_SUFFIXES = [
    " Common Stock", " Common Shares", " Ordinary Shares", " Class A Common Stock",
    " Class B Common Stock", " Class C Capital Stock", " Class A Ordinary Shares",
    " American Depositary Shares", " Class A", " Class B", " Class C",
    " Capital Stock", " Common", ", Inc.", " (The)",
]


def _clean_name(name: str) -> str:
    import re
    n = (name or "").strip()
    # Drop trailing parentheticals like "(Each representing 1 Common Share)".
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    for suf in _NAME_SUFFIXES:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    return n or name


def _norm_symbol(sym: str) -> str:
    return (sym or "").strip().upper().replace(".", "-").replace("/", "-")


def _fetch_exchange_tickers() -> list[dict]:
    """NASDAQ + NYSE full tickers (with marketCap) from the rreichel3 mirror."""
    import json
    base = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main"
    out: list[dict] = []
    for ex in ("nasdaq", "nyse"):
        try:
            data = json.loads(_http_get(f"{base}/{ex}/{ex}_full_tickers.json"))
            out.extend(data)
        except Exception as e:
            print(f"[WARN] {ex} tickers fetch failed: {e}")
    return out


def _cap(d: dict) -> float:
    try:
        return float(d.get("marketCap") or 0)
    except (TypeError, ValueError):
        return 0.0


def build(target: int = 700) -> list[dict]:
    print("Fetching S&P 500 constituents (datahub)...")
    sp500 = _fetch_sp500_datahub()
    print(f"  Got {len(sp500)} symbols.")

    # Symbols normalized to dash form (BRK-B) to match yfinance / our DB.
    # The Alpaca adapter converts dash->dot at its boundary.
    seen: dict[str, str] = {}

    def add(sym: str, name: str) -> None:
        s = _norm_symbol(sym)
        if s and s not in seen:
            seen[s] = _clean_name(name)

    # 1) Guaranteed inclusions: S&P 500 + curated ADRs/ETFs/growth names.
    for sym, name in sp500:
        add(sym, name)
    for sym, name in EXTRA:
        add(sym, name)

    # 2) Top up to `target` with the largest-cap names from the exchanges.
    print("Fetching NASDAQ + NYSE tickers (ranked by market cap)...")
    exch = _fetch_exchange_tickers()
    print(f"  Got {len(exch)} exchange tickers.")
    for d in sorted(exch, key=_cap, reverse=True):
        if len(seen) >= target:
            break
        sym = d.get("symbol", "")
        # Skip warrants/units/rights and odd tickers.
        if not sym or any(c in sym for c in ("^", "=")) or len(sym) > 6:
            continue
        add(sym, d.get("name", sym))

    universe = [{"symbol": k, "name": v} for k, v in sorted(seen.items())]
    print(f"Total unique symbols: {len(universe)}")
    return universe


if __name__ == "__main__":
    universe = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(universe, f, ensure_ascii=False, indent=2)
    print(f"Written → {OUTPUT}")
