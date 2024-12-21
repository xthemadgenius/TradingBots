import argparse
import json
import time
import requests
import sqlite3
from typing import List, Dict


##########################################################################
# TELEGRAM NOTIFIER
##########################################################################
def send_telegram_message(bot_token: str, chat_id: str, text: str):
    """
    Sends a simple message to a given Telegram chat using the Telegram Bot API.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Telegram message sending failed: {e}")


##########################################################################
# FAKE VOLUME CHECK
##########################################################################
def naive_fake_volume_check(token_info: dict) -> bool:
    """
    Simple heuristic checks to label volume as 'fake' or suspicious.
    Example:
     - If 24h volume > 2 * market cap => suspicious
     - If FDV == 0 but volume is large => suspicious
    """
    volume_24h = token_info.get('volume_24h', 0)
    market_cap = token_info.get('market_cap', 0)
    fdv = token_info.get('fdv', 0)

    if market_cap > 0 and volume_24h > 2 * market_cap:
        return True
    if fdv == 0 and volume_24h > 50_000:
        return True
    return False


def pocket_universe_check(token_info: dict, api_url: str, api_key: str) -> bool:
    """
    Hypothetical call to the Pocket Universe API to check if volume is fake.
    You must adapt this to the real Pocket Universe endpoint & response.
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "tokenAddress": token_info.get('address', ''),
            "chain": token_info.get('chain', ''),
            "volume": token_info.get('volume_24h', 0),
            "marketCap": token_info.get('market_cap', 0),
            "fdv": token_info.get('fdv', 0)
        }
        response = requests.post(api_url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        # Suppose the API returns { "isFake": true/false }
        return bool(data.get("isFake", False))
    except requests.RequestException as e:
        print(f"[ERROR] Pocket Universe API error: {e}")
        return False


def is_fake_volume(token_info: dict, config: dict) -> bool:
    """
    Main function to decide if a token has fake volume,
    combining naive check & optional Pocket Universe check.
    """
    if not config.get("check_fake_volume", False):
        return False  # If check is disabled in config, skip.

    # Naive check first
    if naive_fake_volume_check(token_info):
        return True

    # Optional Pocket Universe check
    pu_conf = config.get("pocket_universe", {})
    if pu_conf.get("use_pocket_universe_api", False):
        api_url = pu_conf.get("api_url", "")
        api_key = pu_conf.get("api_key", "")
        if api_url and api_key:
            if pocket_universe_check(token_info, api_url, api_key):
                return True

    return False


##########################################################################
# RUGCHECK.XYZ CHECK (Placeholder)
##########################################################################
def rugcheck_token(token_address: str, api_url: str) -> dict:
    """
    Calls the RugCheck.xyz API for the specified token address (hypothetical).
    Example response:
      {
        "status": "Good" | "Warning" | "Danger",
        "supplyBundled": true/false
      }
    Adjust to the real RugCheck.xyz response.
    """
    try:
        query_url = f"{api_url}?address={token_address}"
        response = requests.get(query_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[ERROR] RugCheck.xyz API error for {token_address}: {e}")
        return {}


def is_good_rugcheck(data: dict) -> bool:
    """Returns True if RugCheck status is 'Good'."""
    return data.get('status') == 'Good'


def is_bundled_supply(data: dict) -> bool:
    """Returns True if the supply is flagged as bundled in RugCheck data."""
    return bool(data.get('supplyBundled', False))


##########################################################################
# DATABASE MANAGEMENT
##########################################################################
def init_db(db_file: str):
    """
    Create or initialize the SQLite database for storing token snapshots.
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            name TEXT,
            symbol TEXT,
            chain TEXT,
            price REAL,
            volume_24h REAL,
            fdv REAL,
            market_cap REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_token_data(db_file: str, token_data_list: List[dict]):
    """
    Bulk inserts token data into the tokens table.
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    for token_data in token_data_list:
        cursor.execute("""
            INSERT INTO tokens (address, name, symbol, chain, price, volume_24h, fdv, market_cap)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token_data.get('address'),
            token_data.get('name'),
            token_data.get('symbol'),
            token_data.get('chain'),
            token_data.get('price'),
            token_data.get('volume_24h'),
            token_data.get('fdv'),
            token_data.get('market_cap'),
        ))
    conn.commit()
    conn.close()


##########################################################################
# ANALYZER (Rug pulls, Pumps, Tier-1)
##########################################################################
def detect_rug_pulls(token_records: List[dict]) -> List[dict]:
    """
    Detect potential rug pulls by comparing market cap to FDV or other heuristics.
    Example: If market_cap < 30% of FDV, suspicious.
    """
    suspicious_tokens = []
    for record in token_records:
        fdv = record.get('fdv', 0)
        mc = record.get('market_cap', 0)
        if fdv > 0 and mc < 0.3 * fdv:
            suspicious_tokens.append(record)
    return suspicious_tokens


def detect_pumps(token_records: List[dict]) -> List[dict]:
    """
    Detect potential pumps by large volume spikes or other criteria.
    Example: If 24h volume > 1,000,000 => consider it a potential pump.
    """
    pumped_tokens = []
    for record in token_records:
        if record.get('volume_24h', 0) > 1_000_000:
            pumped_tokens.append(record)
    return pumped_tokens


def detect_tier_one_listings(token_records: List[dict], known_listings: set) -> List[dict]:
    """
    Check if token's symbol is among known Tier-1 listings (e.g., BTC, ETH, BNB, XRP).
    """
    t1_coins = []
    for record in token_records:
        if record['symbol'] in known_listings:
            t1_coins.append(record)
    return t1_coins


def analyze_tokens(token_data_list: List[dict]) -> dict:
    """
    Runs detection logic and returns a dictionary with lists of suspicious or notable tokens.
    """
    rug_pull_candidates = detect_rug_pulls(token_data_list)
    pump_candidates = detect_pumps(token_data_list)
    tier_one_candidates = detect_tier_one_listings(token_data_list, {"BTC", "ETH", "BNB", "XRP"})

    return {
        "rug_pulls": rug_pull_candidates,
        "pumps": pump_candidates,
        "tier_ones": tier_one_candidates
    }


##########################################################################
# PNL TRACKER
##########################################################################
class PnLTracker:
    """
    Tracks your positions (quantity, cost basis) and calculates unrealized PnL.
    Sends Telegram notifications if the PnL changes beyond a threshold.
    """
    def __init__(self, positions: List[Dict], notify_threshold_percent: float):
        """
        :param positions: e.g. [{"token_address": "0x123...", "quantity": 1000, "cost_basis": 0.05}, ...]
        :param notify_threshold_percent: e.g. 10 => only notify if PnL changes by 10% or more from last check.
        """
        self.positions = positions
        self.notify_threshold_percent = notify_threshold_percent
        self.last_pnl_percent = {}  # {token_address: last_pnl% we recorded}

    def update_prices_and_check(
            self, 
            token_data_list: List[dict],
            send_notification_callback
    ):
        """
        For each token in token_data_list, check if we have a position.
        If yes, compute PnL => compare with last recorded => notify if threshold is crossed.
        """
        for token_info in token_data_list:
            address = token_info.get("address", "").lower()
            current_price = token_info.get("price", 0)

            # Find if we have a position in this token
            for pos in self.positions:
                if pos["token_address"].lower() == address:
                    cost_basis = pos["cost_basis"]
                    quantity = pos["quantity"]
                    pnl = (current_price - cost_basis) * quantity

                    # Avoid divide-by-zero
                    if cost_basis > 0:
                        pnl_percent = ((current_price - cost_basis) / cost_basis) * 100
                    else:
                        pnl_percent = 0

                    last_percent = self.last_pnl_percent.get(address, 0)
                    # Check if PnL changed more than threshold
                    if abs(pnl_percent - last_percent) >= self.notify_threshold_percent:
                        sign = "+" if pnl >= 0 else "-"
                        msg = (
                            f"PnL Update for {token_info.get('symbol', 'Unknown')}:\n"
                            f"Price: ${current_price:.4f}\n"
                            f"PnL: {sign}${abs(pnl):,.2f} ({pnl_percent:.2f}%)\n"
                            f"Quantity: {quantity}\n"
                            f"Cost Basis: ${cost_basis:.4f}\n"
                        )
                        send_notification_callback(msg)

                    # Update last known PnL% for this token
                    self.last_pnl_percent[address] = pnl_percent


##########################################################################
# BONKBOT TRADING (Placeholder)
##########################################################################
def bonkbot_trade(token_info: dict, side: str, amount: float, config: dict, notify_callback):
    """
    A placeholder function simulating a REST-based trade execution with BonkBot.
    In reality, adapt to BonkBot's actual API or Telegram command interface.
    """
    bonk_config = config.get("bonkbot", {})
    if not bonk_config.get("enable_bonkbot_trading", False):
        return  # Trading disabled

    bonkbot_api_url = bonk_config.get("bonkbot_api_url", "")
    slippage = bonk_config.get("preferred_slippage", 0.5)

    payload = {
        "token_address": token_info.get("address", ""),
        "symbol": token_info.get("symbol", ""),
        "chain": token_info.get("chain", ""),
        "side": side,   # "buy" or "sell"
        "amount": amount,
        "slippage": slippage
    }

    try:
        response = requests.post(bonkbot_api_url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if bonk_config.get("trade_notifications", False):
            msg = (f"BonkBot {side.upper()} executed for {token_info.get('symbol','?')}:\n"
                   f"Quantity: {amount}\n"
                   f"Slippage: {slippage}%\n"
                   f"Result: {data}")
            notify_callback(msg)
    except requests.RequestException as e:
        print(f"[ERROR] BonkBot trade call failed: {e}")


##########################################################################
# FETCHING FROM DEXSCREENER (APPLYING SUGGESTED FIXES)
##########################################################################
def fetch_pairs_data(chain: str = "ethereum") -> List[dict]:
    """
    Fetch pairs/tokens from Dexscreener's official API reference:
      GET /latest/dex/pairs/{chain}
    
    We now handle:
    - 'priceUsd' -> price
    - 'volumeUsd24h' -> volume_24h
    - 'fdv'
    - 'liquidity.usd' -> market_cap
    And do basic rate-limit handling if 429 is encountered.
    """
    base_url = "https://api.dexscreener.com/latest/dex"
    url = f"{base_url}/pairs/{chain}"

    try:
        response = requests.get(url, timeout=10)
        # Basic rate-limit check
        if response.status_code == 429:
            print("[ERROR] Rate-limited by DexScreener. Sleeping for 30s...")
            time.sleep(30)
            return []
        response.raise_for_status()

        data = response.json()
        pairs = data.get('pairs', [])
        return pairs

    except requests.RequestException as e:
        print(f"[ERROR] Fetching Dexscreener data failed: {e}")
        return []


def watch_tokens(config: dict):
    """
    Generator that repeatedly fetches data from Dexscreener, 
    applies filters/blacklists, checks RugCheck & fake volume,
    yields valid tokens each loop.
    
    - volumeUsd24h -> token_info['volume_24h']
    - priceUsd -> token_info['price']
    - fdv -> token_info['fdv']
    - liquidity.usd -> token_info['market_cap']
    """
    interval = config.get("interval_seconds", 60)
    chain = config.get("chain", "ethereum")
    filters = config.get("filters", {})

    blacklist_coins = set(config.get("blacklist_coins", []))

    # RugCheck config
    rugcheck_cfg = config.get("rugcheck_xyz", {})
    use_rugcheck = rugcheck_cfg.get("use_rugcheck", False)
    rugcheck_api_url = rugcheck_cfg.get("api_url", "")
    auto_blacklist_if_bundled = rugcheck_cfg.get("auto_blacklist_if_bundled", True)

    while True:
        pairs = fetch_pairs_data(chain=chain)
        parsed_data = []

        for pair in pairs:
            token_address = pair.get('pairAddress', '')
            base_token = pair.get('baseToken', {})

            # Check blacklists
            if token_address in blacklist_coins:
                continue

            # Build token_info from official Dexscreener fields
            token_info = {
                'address': token_address,
                'name': base_token.get('name', ''),
                'symbol': base_token.get('symbol', ''),
                'chain': chain,
                'price': float(pair.get('priceUsd', 0)),                  # from "priceUsd"
                'volume_24h': float(pair.get('volumeUsd24h', 0)),         # from "volumeUsd24h"
                'fdv': float(pair.get('fdv', 0)),                         # from "fdv"
                'market_cap': float(pair.get('liquidity', {}).get('usd', 0))  # from "liquidity.usd"
            }

            # Apply numeric filters
            if token_info['market_cap'] < filters.get('min_market_cap', 0):
                continue
            if token_info['price'] < filters.get('min_price', 0):
                continue
            if token_info['volume_24h'] < filters.get('min_volume_24h', 0):
                continue

            # Check fake volume
            if is_fake_volume(token_info, config):
                continue

            # RugCheck (if enabled)
            if use_rugcheck and rugcheck_api_url:
                rc_data = rugcheck_token(token_address, rugcheck_api_url)
                if not rc_data:
                    continue  # skip if no data returned
                # Only accept if 'status' is Good
                if not is_good_rugcheck(rc_data):
                    continue
                # If supply is bundled => auto-blacklist token
                if is_bundled_supply(rc_data):
                    if auto_blacklist_if_bundled:
                        blacklist_coins.add(token_address)
                    continue

            parsed_data.append(token_info)

        # Persist updated blacklists to config for next iteration
        config["blacklist_coins"] = list(blacklist_coins)

        yield parsed_data
        time.sleep(interval)


##########################################################################
# MAIN BOT CLASS
##########################################################################
class DexScreenerBot:
    """
    Orchestrates:
      - Dexscreener data fetching & filtering
      - DB saving
      - Analysis (rug pulls, pumps, tier-1)
      - PnL tracking
      - (Optionally) trades via BonkBot
      - Telegram notifications
    """
    def __init__(self, config: dict):
        self.config = config
        self.db_file = config.get('db_file', 'dexscreener_data.db')

        # Initialize DB
        init_db(self.db_file)

        # Telegram
        self.telegram_config = config.get("telegram", {})
        self.telegram_enabled = self.telegram_config.get("enable_telegram_notifications", False)
        self.bot_token = self.telegram_config.get("bot_token", "")
        self.chat_id = self.telegram_config.get("chat_id", "")

        # PnL Tracker
        pnl_config = config.get("pnl", {})
        positions = pnl_config.get("positions", [])
        notify_threshold_percent = pnl_config.get("notify_threshold_percent", 10)
        self.pnl_tracker = PnLTracker(positions, notify_threshold_percent)

    def telegram_callback(self, text_msg: str):
        """
        Wraps the Telegram sending function. If Telegram is disabled or missing credentials,
        we just print the message.
        """
        if self.telegram_enabled and self.bot_token and self.chat_id:
            send_telegram_message(self.bot_token, self.chat_id, text_msg)
        else:
            print(f"[TELEGRAM DISABLED] {text_msg}")

    def run(self):
        """
        Main loop:
          1) Watches tokens from Dexscreener
          2) Saves valid data to DB
          3) Analyzes (rug/pump/tier-1)
          4) Sends alerts
          5) Tracks PnL
          6) (Optionally) trades with BonkBot
        """
        tokens_stream = watch_tokens(self.config)
        for token_batch in tokens_stream:
            if not token_batch:
                print("No tokens received in this batch.")
                continue

            # Save batch to DB
            save_token_data(self.db_file, token_batch)

            # Analyze
            analysis_results = analyze_tokens(token_batch)

            # Rug Pull alerts
            if analysis_results["rug_pulls"]:
                msg = "[ALERT] Potential Rug Pulls detected:\n"
                for rp in analysis_results["rug_pulls"]:
                    msg += f"- {rp}\n"
                self.telegram_callback(msg)

            # Pump alerts
            if analysis_results["pumps"]:
                msg = "[INFO] Potential Pumps detected:\n"
                for p in analysis_results["pumps"]:
                    msg += f"- {p}\n"
                self.telegram_callback(msg)

            # Tier-1 listings
            if analysis_results["tier_ones"]:
                msg = "[INFO] Tokens in Tier-1 (known) found:\n"
                for t1 in analysis_results["tier_ones"]:
                    msg += f"- {t1}\n"
                self.telegram_callback(msg)

            # Update PnL & notify if changed beyond threshold
            self.pnl_tracker.update_prices_and_check(token_batch, self.telegram_callback)

            # Example of simple auto-trade logic
            for token_info in token_batch:
                # If symbol == "XYZ" and price < 0.01 => BUY 100 units
                if token_info['symbol'] == "XYZ" and token_info['price'] < 0.01:
                    bonkbot_trade(
                        token_info,
                        side="buy",
                        amount=100,   # e.g., 100 tokens
                        config=self.config,
                        notify_callback=self.telegram_callback
                    )
                # Additional conditions for 'sell' can go here.


##########################################################################
# SCRIPT ENTRY POINT
##########################################################################
def load_config(config_path: str) -> dict:
    """
    Load configuration (JSON) from the given path.
    """
    with open(config_path, 'r') as f:
        return json.load(f)


def parse_arguments():
    """
    CLI arguments to specify config file path, etc.
    """
    parser = argparse.ArgumentParser(description="DexScreener Bot with updated logic for volume & dev fields.")
    parser.add_argument("--config", type=str, default="config.json", help="Path to the config JSON file.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    config_data = load_config(args.config)

    bot = DexScreenerBot(config_data)
    bot.run()
