import requests
import time
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.transaction import Transaction
from solana.system_program import transfer
from solana.rpc.commitment import Confirmed
import logging

# Logging configuration
logging.basicConfig(filename="nft_mev_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Constants
MAGIC_EDEN_API = "https://api-mainnet.magiceden.dev/v2"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
MAX_SPENDING_LIMIT_SOL = 10  # Limit spending per session
TARGET_COLLECTION = "degods"  # Target collection for MEV
BUY_THRESHOLD = 0.85  # Buy if price < 85% of floor price
MEV_GAS_PRIORITY = 100000  # Example gas priority setting

# Initialize Solana client
solana_client = Client(SOLANA_RPC)

# User wallet configuration
WALLET_PRIVATE_KEY = "your_private_key_here"
WALLET_PUBLIC_KEY = "your_public_key_here"

# Fetch floor price
def fetch_floor_price(collection_symbol):
    url = f"{MAGIC_EDEN_API}/collections/{collection_symbol}/stats"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get("floorPrice", None) / 10**9  # Convert lamports to SOL
    else:
        logging.error(f"Error fetching floor price: {response.text}")
        return None

# Fetch new listings
def fetch_new_listings(collection_symbol):
    url = f"{MAGIC_EDEN_API}/collections/{collection_symbol}/listings"
    response = requests.get(url)
    if response.status_code == 200:
        return sorted(response.json(), key=lambda x: x["price"])  # Sort by price
    else:
        logging.error(f"Error fetching listings: {response.text}")
        return []

# Check mempool for pending transactions (Pseudo-code)
def monitor_mempool():
    # Solana does not expose a public mempool; use RPC/WebSocket to monitor pending state changes
    logging.info("Monitoring mempool for opportunities...")
    # Implement Solana WebSocket-based logic here

# Execute MEV-optimized trade
def execute_mev_trade(mint_address, price):
    try:
        logging.info(f"Attempting MEV trade for {mint_address} at {price} SOL")
        # Construct and send a high-priority transaction
        tx = Transaction()
        tx.add(transfer(from_pubkey=WALLET_PUBLIC_KEY, to_pubkey=mint_address, lamports=int(price * 10**9)))
        response = solana_client.send_transaction(tx, WALLET_PRIVATE_KEY, opts=TxOpts(skip_confirmation=False, preflight_commitment=Confirmed))
        logging.info(f"Transaction successful: {response}")
    except Exception as e:
        logging.error(f"Error executing MEV trade for {mint_address}: {str(e)}")

# Trading strategy with MEV
def mev_strategy(collection_symbol):
    floor_price = fetch_floor_price(collection_symbol)
    if floor_price is None:
        logging.error("Unable to fetch floor price. Skipping MEV strategy.")
        return

    logging.info(f"Floor price for {collection_symbol}: {floor_price} SOL")
    nft_listings = fetch_new_listings(collection_symbol)
    for nft in nft_listings:
        price = nft.get("price", 0)
        mint_address = nft.get("mintAddress")
        if price < floor_price * BUY_THRESHOLD:
            logging.info(f"MEV opportunity detected: {mint_address} at {price} SOL")
            execute_mev_trade(mint_address, price)

# Main loop
if __name__ == "__main__":
    logging.info("Starting NFT MEV trading bot...")
    try:
        while True:
            mev_strategy(TARGET_COLLECTION)
            time.sleep(5)  # Adjust based on desired frequency
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")