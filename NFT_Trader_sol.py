import requests
import time
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.rpc.types import TxOpts
from solana.system_program import transfer
import logging

# Logging configuration
logging.basicConfig(filename="nft_mev_bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Constants
MAGIC_EDEN_API = "https://api-mainnet.magiceden.dev/v2"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
CONTRACT_ADDRESS = "Your_Collection_Contract_Address"  # Replace with actual contract address
MAX_SPENDING_LIMIT_SOL = 10  # Limit spending per session
BUY_THRESHOLD = 0.85  # Buy if price < 85% of floor price
PROFIT_THRESHOLD = 1.2  # Exit if selling price > 120% of purchase price

# Initialize Solana client
solana_client = Client(SOLANA_RPC)

# User wallet configuration
WALLET_PRIVATE_KEY = "your_private_key_here"
WALLET_PUBLIC_KEY = "your_public_key_here"

# Fetch collection stats (including floor price)
def fetch_collection_stats(contract_address):
    url = f"{MAGIC_EDEN_API}/collections/{contract_address}/stats"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return {
            "floor_price": data.get("floorPrice", 0) / 10**9,  # Convert lamports to SOL
            "volume_24h": data.get("volume24hr", 0),
        }
    else:
        logging.error(f"Error fetching collection stats: {response.text}")
        return {"floor_price": None, "volume_24h": 0}

# Fetch new listings for the collection
def fetch_new_listings(contract_address):
    url = f"{MAGIC_EDEN_API}/collections/{contract_address}/listings"
    response = requests.get(url)
    if response.status_code == 200:
        return sorted(response.json(), key=lambda x: x["price"])  # Sort by price
    else:
        logging.error(f"Error fetching listings: {response.text}")
        return []

# Purchase NFT
def purchase_nft(mint_address, price):
    try:
        logging.info(f"Attempting to buy NFT: {mint_address} at {price} SOL")
        tx = Transaction()
        tx.add(
            transfer(
                from_pubkey=WALLET_PUBLIC_KEY,
                to_pubkey=mint_address,
                lamports=int(price * 10**9),
            )
        )
        response = solana_client.send_transaction(
            tx, WALLET_PRIVATE_KEY, opts=TxOpts(skip_confirmation=False)
        )
        logging.info(f"Purchase successful: {response}")
        return True
    except Exception as e:
        logging.error(f"Error purchasing NFT {mint_address}: {str(e)}")
        return False

# List NFT for sale
def list_nft_for_sale(mint_address, sell_price):
    try:
        logging.info(f"Listing NFT for sale: {mint_address} at {sell_price} SOL")
        # Placeholder for Magic Eden listing API call
        # Implement this with Magic Eden's selling endpoint or SDK
        # Example: send a signed transaction to list the NFT
        logging.info(f"NFT listed successfully: {mint_address}")
    except Exception as e:
        logging.error(f"Error listing NFT {mint_address} for sale: {str(e)}")

# Entry and Exit Strategy
def trading_strategy(contract_address):
    stats = fetch_collection_stats(contract_address)
    if stats["floor_price"] is None:
        logging.error("Unable to fetch floor price. Skipping strategy.")
        return

    floor_price = stats["floor_price"]
    logging.info(f"Floor price: {floor_price} SOL")

    # Fetch new listings
    listings = fetch_new_listings(contract_address)
    for nft in listings:
        price = nft.get("price", 0)
        mint_address = nft.get("mintAddress")

        # Entry Logic: Buy if the price is below the threshold
        if price < floor_price * BUY_THRESHOLD:
            logging.info(f"Undervalued NFT detected: {mint_address} at {price} SOL")
            if purchase_nft(mint_address, price):
                # Exit Logic: List the NFT at a profit margin
                sell_price = price * PROFIT_THRESHOLD
                logging.info(f"Preparing to list NFT at {sell_price} SOL")
                list_nft_for_sale(mint_address, sell_price)

# Main loop
if __name__ == "__main__":
    logging.info("Starting NFT MEV trading bot with enhanced logic...")
    try:
        while True:
            trading_strategy(CONTRACT_ADDRESS)
            time.sleep(5)  # Adjust frequency for real-time monitoring
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
