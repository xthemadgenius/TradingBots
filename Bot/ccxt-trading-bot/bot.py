import os, time, math, logging, traceback
import pandas as pd
import ccxt
import yaml
from dotenv import load_dotenv

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def setup_logger(level_str="INFO"):
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    return logging.getLogger("ccxt-bot")

def make_exchange(cfg, log):
    exch_id = cfg["exchange"]
    klass = getattr(ccxt, exch_id)
    apiKey = os.getenv(f"{exch_id.upper()}_API_KEY", None)
    secret = os.getenv(f"{exch_id.upper()}_SECRET", None)
    password = os.getenv(f"{exch_id.upper()}_PASSWORD", None) or None

    kwargs = {
        "apiKey": apiKey,
        "secret": secret,
        "enableRateLimit": True,
    }
    # some exchanges require 'password' (passphrase) param
    if password:
        kwargs["password"] = password

    exchange = klass(kwargs)

    # sandbox / testnet if supported
    try:
        if cfg.get("sandbox", False) and hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(True)
            log.info("Sandbox mode: ON")
    except Exception as e:
        log.warning(f"Could not enable sandbox: {e}")

    exchange.load_markets()
    return exchange

def fetch_ohlcv_df(exchange, symbol, timeframe, limit=200):
    data = exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df

def sma_cross_signal(df, fast=20, slow=50):
    if len(df) < slow + 2:
        return None, df
    df = df.copy()
    df["sma_fast"] = df["close"].rolling(fast).mean()
    df["sma_slow"] = df["close"].rolling(slow).mean()
    # Use CLOSED candles
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    signal = None
    if prev["sma_fast"] <= prev["sma_slow"] and curr["sma_fast"] > curr["sma_slow"]:
        signal = "BUY"
    elif prev["sma_fast"] >= prev["sma_slow"] and curr["sma_fast"] < curr["sma_slow"]:
        signal = "SELL"
    return signal, df

def get_balances(exchange, base_ccy, quote_ccy):
    bal = exchange.fetch_balance()
    base_free = (bal.get(base_ccy, {}) or {}).get("free", 0) or 0
    quote_free = (bal.get(quote_ccy, {}) or {}).get("free", 0) or 0
    return float(base_free), float(quote_free)

def clamp_to_market(exchange, market, amount, price=None):
    # respect precision and min limits
    amt = float(exchange.amount_to_precision(market["symbol"], amount))
    min_amt = (market.get("limits", {}).get("amount", {}) or {}).get("min", None)
    if min_amt:
        amt = max(amt, float(min_amt))
    if price is not None:
        price = float(exchange.price_to_precision(market["symbol"], price))
    return amt, price

def place_order(exchange, symbol, side, amount, log, dry_run=True):
    if dry_run:
        log.info(f"[DRY-RUN] {side} {amount} {symbol}")
        return {"id": "dry-run", "status": "mock"}
    order = exchange.create_order(symbol=symbol, type="market", side=side, amount=amount)
    log.info(f"Order placed: {order}")
    return order

def run():
    load_dotenv()
    cfg = load_config()
    log = setup_logger(cfg.get("runtime", {}).get("log_level", "INFO"))
    exchange = make_exchange(cfg, log)
    symbol = cfg["symbol"]
    timeframe = cfg["timeframe"]
    limit = int(cfg.get("candles_limit", 200))
    dry_run = bool(cfg.get("dry_run", True))

    market = exchange.market(symbol)
    base_ccy, quote_ccy = market["base"], market["quote"]
    last_candle_ts = None

    fast = int(cfg["strategy"]["fast"])
    slow = int(cfg["strategy"]["slow"])

    quote_per_trade = float(cfg["risk"]["quote_per_trade"])
    max_position_quote = float(cfg["risk"]["max_position_quote"])
    min_quote_balance = float(cfg["risk"]["min_quote_balance"])
    sell_fraction = float(cfg["risk"]["sell_fraction"])

    poll_interval = int(cfg["runtime"]["poll_interval_sec"])

    log.info(f"Starting bot on {exchange.id} {symbol} {timeframe} | dry_run={dry_run}")
    while True:
        try:
            df = fetch_ohlcv_df(exchange, symbol, timeframe, limit=max(limit, slow+5))
            # act only on new closed candle
            curr_last_ts = int(df.iloc[-1]["ts"].value)
            if last_candle_ts is not None and curr_last_ts == last_candle_ts:
                time.sleep(poll_interval)
                continue
            last_candle_ts = curr_last_ts

            signal, df_sig = sma_cross_signal(df, fast, slow)
            last_close = float(df_sig["close"].iloc[-1])

            base_free, quote_free = get_balances(exchange, base_ccy, quote_ccy)
            pos_quote_value = base_free * last_close

            log.info(f"Candle closed @ {df_sig['ts'].iloc[-1]} | close={last_close:.2f} | "
                     f"{base_ccy}_free={base_free:.6f} (~{pos_quote_value:.2f} {quote_ccy}) "
                     f"{quote_ccy}_free={quote_free:.2f}")

            if signal == "BUY":
                if quote_free < max(min_quote_balance, 1e-9):
                    log.info("Insufficient quote balance, skipping BUY")
                elif pos_quote_value >= max_position_quote:
                    log.info("Position at or above cap, skipping BUY")
                else:
                    spend = min(quote_per_trade, max_position_quote - pos_quote_value, quote_free)
                    if spend <= 0:
                        log.info("Nothing to spend, skipping BUY")
                    else:
                        amount = spend / last_close
                        amount, _ = clamp_to_market(exchange, market, amount)
                        if amount > 0:
                            place_order(exchange, symbol, "buy", amount, log, dry_run=dry_run)
                        else:
                            log.info("Amount below market minimum, skipping BUY")

            elif signal == "SELL":
                to_sell = base_free * sell_fraction
                to_sell, _ = clamp_to_market(exchange, market, to_sell)
                if to_sell > 0:
                    place_order(exchange, symbol, "sell", to_sell, log, dry_run=dry_run)
                else:
                    log.info("Nothing to sell or below market min, skipping SELL")
            else:
                log.info("No signal")

        except Exception as e:
            log.error(f"Loop error: {e}\n{traceback.format_exc()}")

        time.sleep(poll_interval)

if __name__ == "__main__":
    run()
