import requests
import time
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from spl.token.constants import WRAPPED_SOL_MINT
from spl.token.client import Token
import logging

# Logging configuration
logging.basicConfig(filename="nft_trading_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Constants
MAGIC_EDEN_API = "https://api-mainnet.magiceden.dev/v2"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
MAX_SPENDING_LIMIT_SOL = 10  # Set a limit for how much SOL to spend
TARGET_COLLECTION = "degods"  # Replace with your desired NFT collection
BUY_THRESHOLD = 0.9  # Buy if listing price < 90% of floor price

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

# Fetch NFTs for sale
def fetch_nfts(collection_symbol):
    url = f"{MAGIC_EDEN_API}/collections/{collection_symbol}/listings"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Error fetching NFTs: {response.text}")
        return []

# Execute a trade
def execute_trade(mint_address, price):
    try:
        logging.info(f"Attempting to buy NFT: {mint_address} at {price} SOL")
        # Example logic to create and send a transaction
        # tx = Transaction()
        # tx.add(transfer(params=TransferParams(from_pubkey=WALLET_PUBLIC_KEY, to_pubkey=mint_address, lamports=price * 10**9)))
        # response = solana_client.send_transaction(tx, WALLET_PRIVATE_KEY)
        # logging.info(f"Transaction successful: {response}")
    except Exception as e:
        logging.error(f"Error executing trade for {mint_address}: {str(e)}")

# Trading strategy
def trading_strategy(collection_symbol):
    floor_price = fetch_floor_price(collection_symbol)
    if floor_price is None:
        logging.error("Unable to fetch floor price. Skipping strategy.")
        return

    logging.info(f"Floor price for {collection_symbol}: {floor_price} SOL")
    nft_listings = fetch_nfts(collection_symbol)
    for nft in nft_listings:
        price = nft.get("price", 0)
        mint_address = nft.get("mintAddress")
        if price < floor_price * BUY_THRESHOLD:
            logging.info(f"Found undervalued NFT: {mint_address} at {price} SOL")
            execute_trade(mint_address, price)

# Main loop
if __name__ == "__main__":
    logging.info("Starting NFT trading bot...")
    try:
        while True:
            trading_strategy(TARGET_COLLECTION)
            time.sleep(60)  # Wait before the next cycle
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
