#!/usr/bin/env python3

"""
Inverse Volatility Trading Bot

Author: Javier Calderon Jr  (https://github.com/xthemadgenius)

This bot allocates portfolio weights inversely proportional to the volatility of selected symbols.
It fetches historical data, calculates volatilities, determines allocation ratios, and executes trades via Alpaca's API.

Prerequisites:
- Python 3.7+
- Required Libraries: yfinance, alpaca-trade-api, schedule
- Alpaca Account with API keys
"""

import argparse
from datetime import datetime, date
import math
import numpy as np
import time
import sys
import yfinance as yf
import logging
import concurrent.futures
import schedule
import alpaca_trade_api as tradeapi
import os

# Configuration and Logging
logging.basicConfig(
    filename='trading_bot.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

# Argument Parsing
def parse_arguments():
    """
    Parses command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description='Inverse Volatility Trading Bot')
    parser.add_argument('-s', '--symbols', type=str, default='UPRO,TMF',
                        help='Comma-separated list of ticker symbols (default: UPRO,TMF)')
    parser.add_argument('-w', '--window_size', type=int, default=20,
                        help='Window size for volatility calculation (default: 20)')
    parser.add_argument('-d', '--days_per_year', type=int, default=252,
                        help='Number of trading days per year (default: 252)')
    parser.add_argument('-t', '--transaction_cost', type=float, default=0.001,
                        help='Transaction cost rate per trade (default: 0.1%%)')
    parser.add_argument('--base_url', type=str, default=None,
                        help='Alpaca API base URL (overrides environment variable)')
    parser.add_argument('--api_key', type=str, default=None,
                        help='Alpaca API Key ID (overrides environment variable)')
    parser.add_argument('--api_secret', type=str, default=None,
                        help='Alpaca API Secret Key (overrides environment variable)')
    return parser.parse_args()

# Fetch and Calculate Volatility and Performance
def get_volatility_and_performance(symbol, window_size=20, num_trading_days=252):
    """
    Fetches historical price data for the given symbol, calculates the annualized volatility
    and performance over the specified window size.

    Parameters:
        symbol (str): The ticker symbol to fetch data for.
        window_size (int): The number of days to calculate volatility and performance.
        num_trading_days (int): Number of trading days in a year for annualization.

    Returns:
        tuple: (volatility, performance)
    """
    try:
        # Fetch historical data
        data = yf.download(symbol, period=f"{int((window_size + 10))}d", interval="1d", progress=False)
        if data.empty:
            raise ValueError(f"No data fetched for symbol: {symbol}")
        close_prices = data['Close'].dropna().values
        if len(close_prices) < window_size + 1:
            raise ValueError(f"Not enough data to calculate volatility for symbol: {symbol}")

        # Calculate log returns
        log_returns = np.log(close_prices[:-1] / close_prices[1:])
        volatilities_in_window = log_returns[-window_size:]

        # Calculate annualized volatility
        volatility = np.std(volatilities_in_window, ddof=1) * np.sqrt(num_trading_days)

        # Calculate performance over the window
        performance = (close_prices[-1] / close_prices[-window_size -1]) - 1.0

        # Check the most recent date
        most_recent_date = data.index[-1].date()
        if (date.today() - most_recent_date).days > 4:
            raise ValueError(f"Today is {date.today()}, but most recent trading day is {most_recent_date}")

        return volatility, performance
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        raise

# Fetch Data with Retries
def fetch_data_with_retries(symbol, window_size=20, retries=3, delay=5, num_trading_days=252):
    """
    Attempts to fetch data with retries in case of transient failures.

    Parameters:
        symbol (str): The ticker symbol.
        window_size (int): Window size for calculations.
        retries (int): Number of retry attempts.
        delay (int): Delay between retries in seconds.
        num_trading_days (int): Number of trading days in a year.

    Returns:
        tuple: (volatility, performance)
    """
    for attempt in range(retries):
        try:
            return get_volatility_and_performance(symbol, window_size, num_trading_days)
        except Exception as e:
            logging.warning(f"Attempt {attempt +1} failed for {symbol}: {e}")
            if attempt < retries -1:
                time.sleep(delay)
            else:
                logging.error(f"All retries failed for {symbol}. Skipping.")
                raise

# Rebalance Portfolio Based on Inverse Volatility
def rebalance_portfolio(volatilities):
    """
    Calculates allocation ratios inversely proportional to volatilities.

    Parameters:
        volatilities (list): List of volatilities for each symbol.

    Returns:
        list: Allocation ratios for each symbol.
    """
    sum_inverse_volatility = sum(1.0 / vol for vol in volatilities)
    allocation_ratios = [(1.0 / vol) / sum_inverse_volatility for vol in volatilities]
    return allocation_ratios

# Execute Trades via Alpaca API
def execute_trades(api, symbols, allocation_ratios, transaction_cost=0.001):
    """
    Executes trades to adjust portfolio allocations based on calculated ratios.

    Parameters:
        api (tradeapi.REST): Alpaca API client instance.
        symbols (list): List of ticker symbols.
        allocation_ratios (list): Allocation ratios for each symbol.
        transaction_cost (float): Estimated transaction cost rate per trade.
    """
    try:
        account = api.get_account()
        portfolio_value = float(account.cash)  # Simplistic approach; consider using total portfolio value

        for symbol, ratio in zip(symbols, allocation_ratios):
            target_value = portfolio_value * ratio
            current_position = api.get_position(symbol).qty if symbol in [pos.symbol for pos in api.list_positions()] else 0.0
            current_price = float(api.get_last_trade(symbol).price)
            target_qty = target_value / current_price
            order_qty = math.floor(abs(target_qty - float(current_position)))

            if target_qty > float(current_position):
                if order_qty > 0:
                    api.submit_order(
                        symbol=symbol,
                        qty=order_qty,
                        side='buy',
                        type='market',
                        time_in_force='gtc'
                    )
                    logging.info(f"Placed buy order for {order_qty} shares of {symbol}")
            elif target_qty < float(current_position):
                if order_qty > 0:
                    api.submit_order(
                        symbol=symbol,
                        qty=order_qty,
                        side='sell',
                        type='market',
                        time_in_force='gtc'
                    )
                    logging.info(f"Placed sell order for {order_qty} shares of {symbol}")
            else:
                logging.info(f"No trade needed for {symbol}")
    except Exception as e:
        logging.error(f"Error executing trades: {e}")

# Log Allocation Details
def log_allocation(symbols, allocation_ratios, volatilities, performances):
    """
    Logs the allocation details.

    Parameters:
        symbols (list): List of ticker symbols.
        allocation_ratios (list): Allocation ratios for each symbol.
        volatilities (list): Volatilities for each symbol.
        performances (list): Performances for each symbol.
    """
    logging.info(f"Portfolio: {symbols}, Date: {date.today()}, Window Size: {window_size}")
    for symbol, ratio, vol, perf in zip(symbols, allocation_ratios, volatilities, performances):
        logging.info(f"{symbol} allocation: {ratio*100:.2f}%, Volatility: {vol:.2f}%, Performance: {perf*100:.2f}%")

# Main Trading Logic
def trade(api, symbols, window_size, num_trading_days, transaction_cost):
    """
    Executes the main trading cycle: fetch data, calculate allocations, execute trades.

    Parameters:
        api (tradeapi.REST): Alpaca API client instance.
        symbols (list): List of ticker symbols.
        window_size (int): Window size for calculations.
        num_trading_days (int): Number of trading days in a year.
        transaction_cost (float): Estimated transaction cost rate per trade.
    """
    logging.info("Starting trading cycle")
    results = {}
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(fetch_data_with_retries, symbol, window_size, 3, 5, num_trading_days): symbol
                for symbol in symbols
            }
            for future in concurrent.futures.as_completed(futures):
                symbol = futures[future]
                try:
                    volatility, performance = future.result()
                    results[symbol] = {'volatility': volatility, 'performance': performance}
                except Exception as e:
                    logging.error(f"Failed to process {symbol}: {e}")

        volatilities = [results[symbol]['volatility'] for symbol in symbols]
        performances = [results[symbol]['performance'] for symbol in symbols]
        allocation_ratios = rebalance_portfolio(volatilities)

        log_allocation(symbols, allocation_ratios, volatilities, performances)

        execute_trades(api, symbols, allocation_ratios, transaction_cost)
        logging.info("Completed trading cycle")
    except Exception as e:
        logging.error(f"Trading cycle failed: {e}")

# Initialize Alpaca API
def initialize_alpaca(args):
    """
    Initializes the Alpaca API client using environment variables or command-line arguments.

    Parameters:
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        tradeapi.REST: Initialized Alpaca API client.
    """
    base_url = args.base_url or os.getenv('APCA_API_BASE_URL')
    api_key = args.api_key or os.getenv('APCA_API_KEY_ID')
    api_secret = args.api_secret or os.getenv('APCA_API_SECRET_KEY')

    if not all([base_url, api_key, api_secret]):
        logging.error("Alpaca API credentials are not fully provided.")
        sys.exit("Error: Alpaca API credentials are missing. Set them as environment variables or provide via command-line arguments.")

    return tradeapi.REST(api_key, api_secret, base_url, api_version='v2')

# Schedule Trading
def schedule_trading(api, symbols, window_size, num_trading_days, transaction_cost):
    """
    Schedules the trading function to run at a specified time daily.

    Parameters:
        api (tradeapi.REST): Alpaca API client instance.
        symbols (list): List of ticker symbols.
        window_size (int): Window size for calculations.
        num_trading_days (int): Number of trading days in a year.
        transaction_cost (float): Estimated transaction cost rate per trade.
    """
    schedule.every().day.at("16:00").do(
        trade, 
        api=api, 
        symbols=symbols, 
        window_size=window_size, 
        num_trading_days=num_trading_days, 
        transaction_cost=transaction_cost
    )
    logging.info("Scheduled trading to run daily at 16:00")

    while True:
        schedule.run_pending()
        time.sleep(1)

# Main Function
if __name__ == "__main__":
    # Parse command-line arguments
    args = parse_arguments()
    symbols = [symbol.strip().upper() for symbol in args.symbols.split(',')]
    window_size = args.window_size
    num_trading_days = args.days_per_year
    transaction_cost = args.transaction_cost

    logging.info("Inverse Volatility Trading Bot Started")
    logging.info(f"Symbols: {symbols}, Window Size: {window_size}, Trading Days/Year: {num_trading_days}")

    # Initialize Alpaca API
    alpaca_api = initialize_alpaca(args)

    # Execute an initial trading cycle
    try:
        trade(alpaca_api, symbols, window_size, num_trading_days, transaction_cost)
    except Exception as e:
        logging.error(f"Initial trading cycle failed: {e}")

    # Schedule future trading cycles
    schedule_trading(alpaca_api, symbols, window_size, num_trading_days, transaction_cost)
