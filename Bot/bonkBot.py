import argparse
import json
import time
import requests
import sqlite3
from typing import List, Dict

##########################################################################
# TELEGRAM NOTIFIER
##########################################################################
def send_telegram_message(bot_token, chat_id, text):
    """
    Sends a simple message to a given Telegram chat.
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
    volume_24h = token_info.get('volume_24h', 0)
    market_cap = token_info.get('market_cap', 0)
    fdv = token_info.get('fdv', 0)
    
    # Example 1: volume > 2 * market_cap is suspicious
    if market_cap > 0 and volume_24h > 2 * market_cap:
        return True
    
    # Example 2: FDV == 0 but volume is large
    if fdv == 0 and volume_24h > 50000:
        return True
    return False

def pocket_universe_check(token_info: dict, api_url: str, api_key: str) -> bool:
    """
    Hypothetical call to Pocket Universe API to check if volume is fake.
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
        if data.get("isFake", False) is True:
            return True
        return False
    except requests.RequestException as e:
        print(f"[ERROR] Pocket Universe API error: {e}")
        # If API fails, treat as not fake
        return False

def is_fake_volume(token_info: dict, config: dict) -> bool:
    """
    Main function to decide if a token has fake volume,
    based on config flags (naive check or Pocket Universe check).
    """
    if not config.get("check_fake_volume", False):
        return False
    
    # Always do a naive check first
    if naive_fake_volume_check(token_info):
        return True

    # If configured, also check Pocket Universe
    pu_config = config.get("pocket_universe", {})
    if pu_config.get("use_pocket_universe_api", False):
        api_url = pu_config.get("api_url", "")
        api_key = pu_config.get("api_key", "")
        if api_url and api_key:
            if pocket_universe_check(token_info, api_url, api_key):
                return True
    
    return False

##########################################################################
# RUGCHECK.XYZ CHECK
##########################################################################
def rugcheck_token(token_address: str, api_url: str) -> dict:
    """
    Calls the RugCheck.xyz API for a specified token address.
    Example response (hypothetical):
    {
      "status": "Good" | "Warning" | "Danger",
      "supplyBundled": true/false,
      "devAddress": "0xDEADBEEF..."
    }
    """
    try:
        url = f"{api_url}?address={token_address}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as e:
        print(f"[ERROR] RugCheck.xyz API error for {token_address}: {e}")
        return {}

def is_good_rugcheck(data: dict) -> bool:
    return data.get('status') == 'Good'

def is_bundled_supply(data: dict) -> bool:
    return bool(data.get('supplyBundled', False))

def get_dev_address(data: dict) -> str:
    return data.get('devAddress', '')

##########################################################################
# DATABASE MANAGEMENT
##########################################################################
def init_db(db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Table for tokens
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
            dev_address TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_token_data(db_file, token_data_list):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    for token_data in token_data_list:
        cursor.execute("""
            INSERT INTO tokens (address, name, symbol, chain, price, volume_24h, fdv, market_cap, dev_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            token_data.get('address'),
            token_data.get('name'),
            token_data.get('symbol'),
            token_data.get('chain'),
            token_data.get('price'),
            token_data.get('volume_24h'),
            token_data.get('fdv'),
            token_data.get('market_cap'),
            token_data.get('dev_address')
        ))
        
    conn.commit()
    conn.close()

##########################################################################
# ANALYZER
##########################################################################
def detect_rug_pulls(token_records: list) -> list:
    suspicious_tokens = []
    for record in token_records:
        # Example logic: if market_cap < 30% of FDV => suspicious
        if record.get('fdv', 0) > 0:
            ratio = record['market_cap'] / record['fdv']
            if ratio < 0.3:
                suspicious_tokens.append(record)
    return suspicious_tokens

def detect_pumps(token_records: list) -> list:
    pumped_tokens = []
    for record in token_records:
        if record.get('volume_24h', 0) > 1000000:  # naive example
            pumped_tokens.append(record)
    return pumped_tokens

def detect_tier_one_listings(token_records: list, known_listings: set) -> list:
    t1_coins = []
    for record in token_records:
        if record['symbol'] in known_listings:
            t1_coins.append(record)
    return t1_coins

def analyze_tokens(token_data_list):
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
    def __init__(self, positions: List[Dict], notify_threshold_percent: float):
        self.positions = positions
        self.notify_threshold_percent = notify_threshold_percent
        self.last_pnl_percent = {}  # key: token_address, value: float

    def update_prices_and_check(self, token_data_list: List[Dict], send_notification_callback):
        for token_info in token_data_list:
            address = token_info.get("address")
            current_price = token_info.get("price", 0)

            # Check if we have a position in this token
            for pos in self.positions:
                if pos["token_address"].lower() == address.lower():
                    cost_basis = pos["cost_basis"]
                    quantity = pos["quantity"]
                    pnl = (current_price - cost_basis) * quantity
                    pnl_percent = 0.0
                    if cost_basis > 0:
                        pnl_percent = ((current_price - cost_basis) / cost_basis) * 100
                    
                    last_percent = self.last_pnl_percent.get(address, 0)
                    if abs(pnl_percent - last_percent) >= self.notify_threshold_percent:
                        # Build the notification text
                        sign = "+" if pnl >= 0 else "-"
                        text = (
                            f"PnL Update for {token_info.get('symbol', 'Unknown')}:\n"
                            f"Price: ${current_price:.4f}\n"
                            f"PnL: {sign}${abs(pnl):,.2f} ({pnl_percent:.2f}%)\n"
                            f"Quantity: {quantity}\n"
                            f"Cost Basis: ${cost_basis:.4f}\n"
                        )
                        send_notification_callback(text)
                    
                    self.last_pnl_percent[address] = pnl_percent

##########################################################################
# BONKBOT TRADING
##########################################################################
def bonkbot_trade(token_info: dict, side: str, amount: float, config: dict, notify_callback):
    """
    A placeholder function to demonstrate trading via BonkBot.
    'side' can be "buy" or "sell".
    'amount' can be quantity or notional (depending on your approach).
    
    We'll just pretend to send a request to some BonkBot endpoint or 
    send a command via Telegram to @BonkBot. Adjust for real usage.
    """
    bonk_config = config.get("bonkbot", {})
    if not bonk_config.get("enable_bonkbot_trading", False):
        return

    bonkbot_api_url = bonk_config.get("bonkbot_api_url")
    slippage = bonk_config.get("preferred_slippage", 0.5)

    # For demonstration, let's assume BonkBot has a REST endpoint 
    # that accepts JSON with token, side, amount, slippage, etc.

    payload = {
        "token_address": token_info["address"],
        "symbol": token_info["symbol"],
        "chain": token_info["chain"],
        "side": side,
        "amount": amount,
        "slippage": slippage
    }

    try:
        response = requests.post(bonkbot_api_url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        # Maybe data returns a result with status, tx hash, etc.
        if bonk_config.get("trade_notifications", False):
            msg = (f"BonkBot {side.upper()} executed for {token_info['symbol']}:\n"
                   f"Quantity: {amount}\n"
                   f"Slippage: {slippage}%\n"
                   f"Result: {data}")
            notify_callback(msg)
    except requests.RequestException as e:
        print(f"[ERROR] BonkBot trade call failed: {e}")

##########################################################################
# DEXSCREENER WATCH
##########################################################################
def fetch_pairs_data(chain: str = "ethereum") -> list:
    DEXSCREENER_BASE_URL = "https://api.dexscreener.com/latest/dex"
    try:
        url = f"{DEXSCREENER_BASE_URL}/pairs/{chain}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'pairs' in data:
            return data['pairs']
        else:
            return []
    except requests.RequestException as e:
        print(f"[ERROR] Fetching data failed: {e}")
        return []

def watch_tokens(config: dict):
    interval = config["interval_seconds"]
    chain = config["chain"]
    filters = config["filters"]
    
    blacklist_coins = set(config.get("blacklist_coins", []))
    dev_blacklist = set(config.get("dev_blacklist", []))
    
    # RugCheck config
    use_rugcheck = config.get("rugcheck_xyz", {}).get("use_rugcheck", False)
    rugcheck_api_url = config.get("rugcheck_xyz", {}).get("api_url", "")
    auto_blacklist_if_bundled = config.get("rugcheck_xyz", {}).get("auto_blacklist_if_bundled", True)

    while True:
        pairs = fetch_pairs_data(chain=chain)
        parsed_data = []
        
        for pair in pairs:
            token_address = pair.get('pairAddress')
            base_token = pair.get('baseToken', {})
            dev_address = pair.get('devAddress', '')  # hypothetical
            
            # Check blacklists
            if token_address in blacklist_coins:
                continue
            if dev_address in dev_blacklist:
                continue

            token_info = {
                'address': token_address,
                'name': base_token.get('name'),
                'symbol': base_token.get('symbol'),
                'chain': chain,
                'price': float(pair.get('priceUsd', 0)),
                'volume_24h': float(pair.get('volume', 0)),
                'fdv': float(pair.get('fdv', 0)),
                'market_cap': float(pair.get('liquidity', {}).get('usd', 0)),
                'dev_address': dev_address
            }

            # Apply filters
            if token_info['market_cap'] < filters.get('min_market_cap', 0):
                continue
            if token_info['price'] < filters.get('min_price', 0):
                continue
            if token_info['volume_24h'] < filters.get('min_volume_24h', 0):
                continue

            # Fake volume check
            if is_fake_volume(token_info, config):
                continue

            # RugCheck
            if use_rugcheck and rugcheck_api_url:
                rc_data = rugcheck_token(token_address, rugcheck_api_url)
                if not rc_data:
                    continue  # skip if no data
                if not is_good_rugcheck(rc_data):
                    continue
                if is_bundled_supply(rc_data):
                    if auto_blacklist_if_bundled:
                        blacklist_coins.add(token_address)
                        dev_addr_rc = get_dev_address(rc_data)
                        if dev_addr_rc:
                            dev_blacklist.add(dev_addr_rc)
                        else:
                            if dev_address:
                                dev_blacklist.add(dev_address)
                    continue

            parsed_data.append(token_info)

        # Update config blacklists in-memory
        config["blacklist_coins"] = list(blacklist_coins)
        config["dev_blacklist"] = list(dev_blacklist)

        yield parsed_data
        time.sleep(interval)

##########################################################################
# MAIN BOT
##########################################################################
class DexScreenerBot:
    def __init__(self, config: dict):
        self.config = config
        self.db_file = config['db_file']

        # Initialize DB
        init_db(self.db_file)

        # Prepare Telegram
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
        if self.telegram_enabled and self.bot_token and self.chat_id:
            send_telegram_message(self.bot_token, self.chat_id, text_msg)
        else:
            print(f"[TELEGRAM DISABLED] Would have sent: {text_msg}")

    def run(self):
        tokens_stream = watch_tokens(self.config)
        for token_batch in tokens_stream:
            if not token_batch:
                print("No tokens received in this batch.")
                continue

            # Save batch
            save_token_data(self.db_file, token_batch)

            # Analyze
            analysis_results = analyze_tokens(token_batch)

            # Rug pull alerts
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

            # Tier-1
            if analysis_results["tier_ones"]:
                msg = "[INFO] Tokens in Tier-1 (known) found:\n"
                for t1 in analysis_results["tier_ones"]:
                    msg += f"- {t1}\n"
                self.telegram_callback(msg)

            # PnL Tracking
            self.pnl_tracker.update_prices_and_check(token_batch, self.telegram_callback)

            # ---------------------------------------------------------
            # EXAMPLE: If you want to trade certain tokens automatically
            # you could add logic here. For instance:
            # ---------------------------------------------------------
            for token_info in token_batch:
                # Example condition: If a token is "XYZ" and price < 0.01
                if token_info['symbol'] == "XYZ" and token_info['price'] < 0.01:
                    # Buy 100 units
                    bonkbot_trade(
                        token_info, 
                        side="buy", 
                        amount=100, 
                        config=self.config,
                        notify_callback=self.telegram_callback
                    )
                # Similarly, you can add "sell" logic, etc.

##########################################################################
# ENTRY POINT
##########################################################################
def load_config(config_path: str) -> dict:
    with open(config_path, 'r') as f:
        return json.load(f)

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.json", help="Path to the config JSON file")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    config = load_config(args.config)

    bot = DexScreenerBot(config)
    bot.run()
