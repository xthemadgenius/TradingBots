import time
import argparse
import requests
import pandas as pd
import logging
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from datetime import datetime

# Initialize and Adjust trading fee percentage
FEE_PERCENTAGE = 0.001  # 0.1% trading fee

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def send_telegram_message(message, telegram_token, chat_id):
    """
    Send a message to a Telegram chat.

    Parameters:
    - message (str): The message to send.
    - telegram_token (str): Telegram bot token.
    - chat_id (str): Telegram chat ID.
    """
    if not telegram_token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    response = requests.post(url, data=payload)
    return response.json()

def get_ema(symbol, interval, length, client):
    """
    Calculate the Exponential Moving Average (EMA) for a given symbol and interval.

    Parameters:
    - symbol (str): Trading pair symbol (e.g., 'BTCUSDT').
    - interval (str): Kline interval (e.g., '1h').
    - length (int): Period over which to calculate EMA.
    - client (Client): Binance API client instance.

    Returns:
    - float: The calculated EMA value.
    """
    # Fetch enough klines to calculate EMA
    klines = client.get_klines(symbol=symbol, interval=interval, limit=length*2)
    closes = [float(entry[4]) for entry in klines]
    df = pd.DataFrame(closes, columns=['Close'])
    ema = df['Close'].ewm(span=length, adjust=False).mean()
    return ema.iloc[-1]

def get_symbol_info(symbol, client):
    """
    Retrieve symbol information from Binance exchange info.

    Parameters:
    - symbol (str): Trading pair symbol (e.g., 'BTCUSDT').
    - client (Client): Binance API client instance.

    Returns:
    - dict: Symbol information.
    """
    exchange_info = client.get_exchange_info()
    symbol_info = next((item for item in exchange_info['symbols'] if item['symbol'] == symbol), None)
    return symbol_info

def get_asset_balance(asset_symbol, client):
    """
    Get the free balance of an asset.

    Parameters:
    - asset_symbol (str): Asset symbol (e.g., 'BTC', 'USDT').
    - client (Client): Binance API client instance.

    Returns:
    - float: Free balance of the asset.
    """
    balance = client.get_asset_balance(asset=asset_symbol)
    return float(balance['free']) if balance and 'free' in balance else 0.0

def get_current_price(symbol, client):
    """
    Get the current price of a trading pair.

    Parameters:
    - symbol (str): Trading pair symbol (e.g., 'BTCUSDT').
    - client (Client): Binance API client instance.

    Returns:
    - float: Current price.
    """
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker['price'])

def main():
    parser = argparse.ArgumentParser(description="Binance Spot Trading Bot based on EMA crossover.")
    parser.add_argument('symbol', type=str, help="Trading pair, e.g., 'BTCUSDT'.")
    parser.add_argument('interval', type=str, help="Interval for fetching data, e.g., '1h', '3d', '1m'.")
    parser.add_argument('short_ema_period', type=int, help="Short EMA period, e.g., 7.")
    parser.add_argument('long_ema_period', type=int, help="Long EMA period, e.g., 25.")
    parser.add_argument('--api_key', type=str, required=False, help="Your Binance API key.")
    parser.add_argument('--api_secret', type=str, required=False, help="Your Binance API secret.")
    parser.add_argument('--trade_amount', type=float, help="Amount in quote currency to trade each time.")
    parser.add_argument('--stop_loss_pct', type=float, default=0.05, help="Stop loss percentage (e.g., 0.05 for 5%).")
    parser.add_argument('--take_profit_pct', type=float, default=0.10, help="Take profit percentage (e.g., 0.10 for 10%).")
    parser.add_argument('--dry_run', action='store_true', help="Run the bot without executing trades.")
    parser.add_argument('--telegram_token', type=str, help="Telegram bot token for notifications.")
    parser.add_argument('--telegram_chat_id', type=str, help="Telegram chat ID for notifications.")
    parser.add_argument('--notify_interval', type=int, default=60, help="Number of iterations between notifications.")

    args = parser.parse_args()

    # Get API keys from environment variables if not provided
    api_key = args.api_key or os.getenv('BINANCE_API_KEY')
    api_secret = args.api_secret or os.getenv('BINANCE_API_SECRET')

    if not api_key or not api_secret:
        logger.error("Binance API key and secret must be provided via command line or environment variables.")
        return

    client = Client(api_key, api_secret)

    # Get symbol info
    symbol_info = get_symbol_info(args.symbol, client)
    if not symbol_info:
        logger.error(f"Symbol {args.symbol} not found.")
        return

    base_asset = symbol_info['baseAsset']
    quote_asset = symbol_info['quoteAsset']

    # Get lot size and min notional filters
    lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
    min_qty = float(lot_size_filter['minQty'])
    step_size = float(lot_size_filter['stepSize'])

    min_notional_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), None)
    min_notional = float(min_notional_filter['minNotional'])

    last_cross = None
    buy_price = None
    buy_amount = 0  # amount of crypto bought
    buy_cost = 0    # cost of the buy in quote currency
    i = 0

    while True:
        try:
            current_price = get_current_price(args.symbol, client)
            short_ema = get_ema(args.symbol, args.interval, args.short_ema_period, client)
            long_ema = get_ema(args.symbol, args.interval, args.long_ema_period, client)

            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

            # Check for EMA crossovers
            if short_ema > long_ema and last_cross != 'above':
                quote_balance = get_asset_balance(quote_asset, client)
                trade_amount = args.trade_amount or quote_balance
                trade_amount = min(trade_amount, quote_balance)
                if trade_amount >= min_notional:
                    logger.info(f"{timestamp} - Short EMA crossed above Long EMA. Placing a BUY order.")
                    send_telegram_message(f"{timestamp} - Short EMA crossed above Long EMA. Placing a BUY order.",
                                          args.telegram_token, args.telegram_chat_id)
                    if args.dry_run:
                        buy_order = {'status': 'FILLED', 'cummulativeQuoteQty': str(trade_amount), 'fills': [{'qty': str(trade_amount / current_price)}]}
                        logger.info("Dry run mode: Buy order simulated.")
                    else:
                        buy_order = client.order_market_buy(symbol=args.symbol, quoteOrderQty=trade_amount)
                    buy_cost = float(buy_order['cummulativeQuoteQty'])  # total cost in quote currency
                    buy_amount = sum([float(fill['qty']) for fill in buy_order['fills']])
                    buy_price = buy_cost / buy_amount  # average buy price

                    if buy_order['status'] == 'FILLED':
                        last_cross = 'above'

            elif short_ema < long_ema and last_cross != 'below':
                base_balance = get_asset_balance(base_asset, client)
                if base_balance >= min_qty:
                    base_balance = base_balance - (base_balance % step_size)  # adjust to step size
                    if base_balance >= min_qty:
                        logger.info(f"{timestamp} - Short EMA crossed below Long EMA. Placing a SELL order.")
                        send_telegram_message(f"{timestamp} - Short EMA crossed below Long EMA. Placing a SELL order.",
                                              args.telegram_token, args.telegram_chat_id)
                        if args.dry_run:
                            sell_order = {'status': 'FILLED', 'cummulativeQuoteQty': str(base_balance * current_price)}
                            logger.info("Dry run mode: Sell order simulated.")
                        else:
                            sell_order = client.order_market_sell(symbol=args.symbol, quantity=base_balance)
                        sell_revenue = float(sell_order['cummulativeQuoteQty'])  # total received in quote currency
                        fee = FEE_PERCENTAGE * sell_revenue
                        pnl = (sell_revenue - fee) - buy_cost  # calculate PNL
                        logger.info(f"PNL: {pnl:.2f} {quote_asset}")
                        send_telegram_message(f"PNL: {pnl:.2f} {quote_asset}", args.telegram_token, args.telegram_chat_id)
                        buy_amount = 0
                        buy_cost = 0
                        buy_price = None

                        if sell_order['status'] == 'FILLED':
                            last_cross = 'below'

            # Check for stop loss and take profit
            if buy_price:
                if current_price <= buy_price * (1 - args.stop_loss_pct):
                    base_balance = get_asset_balance(base_asset, client)
                    if base_balance >= min_qty:
                        base_balance = base_balance - (base_balance % step_size)  # adjust to step size
                        logger.info(f"{timestamp} - Stop loss triggered. Placing a SELL order.")
                        send_telegram_message(f"{timestamp} - Stop loss triggered. Placing a SELL order.",
                                              args.telegram_token, args.telegram_chat_id)
                        if args.dry_run:
                            sell_order = {'status': 'FILLED', 'cummulativeQuoteQty': str(base_balance * current_price)}
                            logger.info("Dry run mode: Stop loss sell order simulated.")
                        else:
                            sell_order = client.order_market_sell(symbol=args.symbol, quantity=base_balance)
                        sell_revenue = float(sell_order['cummulativeQuoteQty'])
                        fee = FEE_PERCENTAGE * sell_revenue
                        pnl = (sell_revenue - fee) - buy_cost
                        logger.info(f"PNL: {pnl:.2f} {quote_asset}")
                        send_telegram_message(f"PNL: {pnl:.2f} {quote_asset}", args.telegram_token, args.telegram_chat_id)
                        buy_amount = 0
                        buy_cost = 0
                        buy_price = None
                        last_cross = 'below'  # reset last_cross to prevent immediate re-buy

                elif current_price >= buy_price * (1 + args.take_profit_pct):
                    base_balance = get_asset_balance(base_asset, client)
                    if base_balance >= min_qty:
                        base_balance = base_balance - (base_balance % step_size)  # adjust to step size
                        logger.info(f"{timestamp} - Take profit target reached. Placing a SELL order.")
                        send_telegram_message(f"{timestamp} - Take profit target reached. Placing a SELL order.",
                                              args.telegram_token, args.telegram_chat_id)
                        if args.dry_run:
                            sell_order = {'status': 'FILLED', 'cummulativeQuoteQty': str(base_balance * current_price)}
                            logger.info("Dry run mode: Take profit sell order simulated.")
                        else:
                            sell_order = client.order_market_sell(symbol=args.symbol, quantity=base_balance)
                        sell_revenue = float(sell_order['cummulativeQuoteQty'])
                        fee = FEE_PERCENTAGE * sell_revenue
                        pnl = (sell_revenue - fee) - buy_cost
                        logger.info(f"PNL: {pnl:.2f} {quote_asset}")
                        send_telegram_message(f"PNL: {pnl:.2f} {quote_asset}", args.telegram_token, args.telegram_chat_id)
                        buy_amount = 0
                        buy_cost = 0
                        buy_price = None
                        last_cross = 'below'  # reset last_cross to prevent immediate re-buy

            print_message = f"{timestamp} - Current Price: {current_price}, Short EMA: {short_ema}, Long EMA: {long_ema}"
            logger.info(print_message)

            i += 1
            if i >= args.notify_interval:
                send_telegram_message(print_message, args.telegram_token, args.telegram_chat_id)
                i = 0

            # Sleep until next interval
            interval_mapping = {'1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '2h': 7200,
                                '4h': 14400, '6h': 21600, '8h': 28800, '12h': 43200, '1d': 86400, '3d': 259200,
                                '1w': 604800, '1M': 2592000}
            sleep_duration = interval_mapping.get(args.interval, 300)
            time_to_sleep = sleep_duration - (time.time() % sleep_duration)
            time.sleep(time_to_sleep)

        except BinanceAPIException as e:
            logger.error(f"Binance API Exception: {e}")
            send_telegram_message(f"Binance API Exception: {e}", args.telegram_token, args.telegram_chat_id)
            time.sleep(60)
        except BinanceOrderException as e:
            logger.error(f"Binance Order Exception: {e}")
            send_telegram_message(f"Binance Order Exception: {e}", args.telegram_token, args.telegram_chat_id)
            time.sleep(60)
        except requests.exceptions.ReadTimeout:
            logger.error("Encountered ReadTimeout. Sleeping for a minute before retrying...")
            send_telegram_message("Encountered ReadTimeout. Sleeping for a minute before retrying...", args.telegram_token, args.telegram_chat_id)
            time.sleep(60)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            send_telegram_message(f"Unexpected error: {e}", args.telegram_token, args.telegram_chat_id)
            time.sleep(60)

if __name__ == "__main__":
    main()


''' 
This bot automates spot trading on Binance based on Exponential Moving Average (EMA) crossovers:

Buy Signal: When the short-term EMA crosses above the long-term EMA (upward momentum) and the last action wasn't a buy, the bot places a buy order.
Sell Signal: When the short-term EMA crosses below the long-term EMA (downward momentum) and the last action wasn't a sell, the bot places a sell order.
How It Works:

Continuously fetches the latest price for the specified symbol.
Calculates short and long EMAs in each loop iteration.
Order Execution Logic:

Buy Order: Checks if the buy order is fully executed before updating the last action to prevent duplicate buys.
Sell Order: Checks if the sell order is fully executed before updating the last action to prevent duplicate sells.
Exception Handling:

Catches API timeouts and other exceptions to ensure the bot continues running without unexpected termination.
''' 

#Run
#python run_bot.py <Symbol> <Interval> <Short EMA Period> <Long EMA Period>

#Example: python run_bot.py BTCUSDT 1d 8 20

#To Run in Background nohup python run_bot.py BTCUSDT 1d 8 20 &
