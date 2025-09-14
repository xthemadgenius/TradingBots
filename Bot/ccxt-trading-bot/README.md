# CCXT SMA Crossover Trading Bot

A minimal, exchange-agnostic trading bot built on [CCXT]. It fetches OHLCV candles,
computes a moving-average crossover, and places market orders with basic risk controls.
Supports sandbox/testnet and a dry-run mode (no orders placed).

## Quick start
```bash
# 1) Create and activate a virtualenv (optional)
python3 -m venv .venv && source .venv/bin/activate

# 2) Install deps
pip install -r requirements.txt

# 3) Configure your keys and settings
cp .env.example .env            # then edit .env
cp config.example.yaml config.yaml  # then edit config.yaml

# 4) Run in dry-run first
python bot.py

# 5) Flip `dry_run: false` in config.yaml when ready
```

## Notes
- Use sandbox/testnet first by setting `sandbox: true` (when supported by your exchange).
- `dry_run: true` logs intended orders without sending them.
- The bot acts at most once per closed candle per symbol.
- Example exchange: `binance` on `BTC/USDT`, timeframe `1h`.
- Strategy: simple SMA(fast) crosses SMA(slow).
