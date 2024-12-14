import numpy as np

def initialize(state):
    """Initialize strategy variables and preload historical data."""
    state['lookback'] = 20
    state['symbol'] = 'AAPL'
    try:
        state['prices'] = get_historical_prices(state['symbol'], state['lookback'])
        print(f"Loaded historical data for {state['symbol']}.")
    except Exception as e:
        print(f"Error initializing strategy: {e}")

def price_event(price, symbol, state):
    """Evaluate the trading signal and execute trades based on moving averages."""
    try:
        prices = get_historical_prices(symbol, state['lookback'])

        # Calculate moving averages
        sma_short = np.mean(prices[-5:])  # 5-day SMA
        sma_long = np.mean(prices)        # 20-day SMA

        # Trading logic
        if sma_short > sma_long:
            print(f"[BUY] {symbol}: SMA short ({sma_short}) > SMA long ({sma_long}).")
            execute_trade(symbol, 'buy', 1)
        elif sma_short < sma_long:
            print(f"[SELL] {symbol}: SMA short ({sma_short}) < SMA long ({sma_long}).")
            execute_trade(symbol, 'sell', 1)
    except Exception as e:
        print(f"Error in price event: {e}")

def get_historical_prices(symbol, lookback):
    """Mock function to fetch historical prices."""
    # Replace with actual API call logic to fetch historical prices
    return np.random.random(lookback) * 100

def execute_trade(symbol, side, size):
    """Mock function to execute a trade."""
    # Replace with actual trade execution logic
    print(f"Executed {side} trade for {size} unit(s) of {symbol}.")

def main():
    """Main entry point for the trading bot."""
    # Initialize state and set up strategy
    state = {}
    initialize(state)

    # Simulate price events for testing
    for _ in range(5):
        price_event(None, state['symbol'], state)

if __name__ == "__main__":
    main()
