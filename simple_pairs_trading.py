# Import necessary libraries
import pandas as pd
import numpy as np
import yfinance as yf
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.stats.multitest import multipletests
import matplotlib.pyplot as plt
import seaborn as sns
import datetime
import warnings
warnings.filterwarnings("ignore")

# Set display options for DataFrames
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 100)

# Function to download S&P 500 symbols
def get_sp500_symbols():
    # Fetch the list from Wikipedia
    table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    df = table[0]
    symbols = df['Symbol'].tolist()
    return symbols

# Function to download historical data for symbols
def download_data(symbols, start_date, end_date):
    data = {}
    for symbol in symbols:
        try:
            # Fetch adjusted close prices
            df = yf.download(symbol, start=start_date, end=end_date)
            data[symbol] = df['Adj Close']
        except Exception as e:
            print(f"Could not download data for {symbol}: {e}")
    prices = pd.DataFrame(data)
    return prices

# Function to find cointegrated pairs with multiple testing correction
def find_cointegrated_pairs(data, significance=0.05):
    n = data.shape[1]
    pvalue_matrix = np.ones((n, n))
    keys = data.columns
    pairs = []
    pvalues = []
    indices = []

    # Collect all p-values
    for i in range(n):
        for j in range(i+1, n):
            S1 = data.iloc[:, i]
            S2 = data.iloc[:, j]
            result = coint(S1, S2)
            pvalue = result[1]
            pvalue_matrix[i, j] = pvalue
            pvalues.append(pvalue)
            indices.append((i, j))

    # Adjust p-values for multiple testing
    _, corrected_pvalues, _, _ = multipletests(pvalues, alpha=significance, method='fdr_bh')

    # Extract pairs with significant cointegration
    for k in range(len(corrected_pvalues)):
        if corrected_pvalues[k] < significance:
            i, j = indices[k]
            pairs.append((keys[i], keys[j]))

    return pvalue_matrix, pairs

# Function to calculate the hedge ratio and spread
def calculate_spread(S1, S2):
    S1 = S1.dropna()
    S2 = S2.dropna()
    min_len = min(len(S1), len(S2))
    S1 = S1[-min_len:]
    S2 = S2[-min_len:]
    S1 = S1.values
    S2 = S2.values
    # Add a constant to S2
    S2_const = sm.add_constant(S2)
    # Perform linear regression
    model = sm.OLS(S1, S2_const).fit()
    hedge_ratio = model.params[1]
    spread = S1 - hedge_ratio * S2
    return spread, hedge_ratio

# Function to check for stationarity
def check_stationarity(spread):
    adf_result = adfuller(spread)
    p_value = adf_result[1]
    return p_value < 0.05  # Returns True if spread is stationary

# Function to calculate half-life of mean reversion
def half_life(spread):
    spread_lag = np.roll(spread, 1)
    spread_ret = spread - spread_lag
    spread_lag = spread_lag[1:]
    spread_ret = spread_ret[1:]
    spread_lag_const = sm.add_constant(spread_lag)
    model = sm.OLS(spread_ret, spread_lag_const).fit()
    halflife = -np.log(2) / model.params[1]
    return int(round(halflife))

# Function to generate trading signals
def generate_signals(spread, window):
    rolling_mean = pd.Series(spread).rolling(window=window).mean()
    rolling_std = pd.Series(spread).rolling(window=window).std()
    z_score = (pd.Series(spread) - rolling_mean) / rolling_std
    signals = pd.Series(index=z_score.index)
    signals[z_score > 1] = -1  # Sell signal
    signals[z_score < -1] = 1   # Buy signal
    signals[(z_score > -0.5) & (z_score < 0.5)] = 0  # Exit signal
    signals = signals.fillna(method='ffill').fillna(0)
    return signals, z_score

# Function to backtest the strategy
def backtest(S1, S2, hedge_ratio, signals, initial_investment=100000, transaction_cost=0.0005, stop_loss=0.05):
    positions = pd.DataFrame(index=signals.index).fillna(0.0)
    positions['S1'] = -signals * 1  # Short or long S1
    positions['S2'] = signals * hedge_ratio  # Long or short S2
    # Compute daily returns
    S1_ret = S1.pct_change().fillna(0)
    S2_ret = S2.pct_change().fillna(0)
    portfolio_returns = positions['S1'] * S1_ret + positions['S2'] * S2_ret
    # Apply transaction costs
    trades = positions.diff().fillna(0)
    transaction_costs = (abs(trades['S1']) * S1_ret.abs() + abs(trades['S2']) * S2_ret.abs()) * transaction_cost
    portfolio_returns -= transaction_costs
    # Calculate cumulative returns
    cumulative_returns = (1 + portfolio_returns).cumprod()
    # Apply stop-loss
    drawdown = (cumulative_returns.cummax() - cumulative_returns) / cumulative_returns.cummax()
    if drawdown.max() > stop_loss:
        stop_idx = drawdown[drawdown > stop_loss].index[0]
        cumulative_returns = cumulative_returns[:stop_idx]
        print(f"Stop-loss triggered on {stop_idx}")
    # Calculate final return
    final_return = cumulative_returns.iloc[-1] * initial_investment
    return cumulative_returns, final_return

# Main execution
if __name__ == "__main__":
    # Parameters
    start_date = '2010-01-01'
    end_date = '2020-12-31'
    significance_level = 0.05

    # Step 1: Get S&P 500 symbols
    symbols = get_sp500_symbols()

    # For demonstration purposes, limit the number of symbols (e.g., first 50)
    symbols = symbols[:50]

    # Step 2: Download historical data
    prices = download_data(symbols, start_date, end_date)

    # Step 3: Preprocess data
    prices = prices.fillna(method='ffill').dropna(axis=1)

    # Step 4: Find cointegrated pairs
    pvalue_matrix, pairs = find_cointegrated_pairs(prices, significance=significance_level)
    print(f"Number of cointegrated pairs found: {len(pairs)}")
    print("Cointegrated pairs:")
    for pair in pairs:
        print(pair)

    # Step 5: Analyze each cointegrated pair
    results = []
    for pair in pairs:
        S1 = prices[pair[0]]
        S2 = prices[pair[1]]
        spread, hedge_ratio = calculate_spread(S1, S2)
        # Check for stationarity
        if check_stationarity(spread):
            # Calculate half-life
            hl = half_life(spread)
            if hl > 0:
                # Generate signals
                signals, z_score = generate_signals(spread, window=hl)
                # Split into training and testing datasets
                split = int(0.7 * len(S1))
                S1_train, S1_test = S1[:split], S1[split:]
                S2_train, S2_test = S2[:split], S2[split:]
                signals_train, signals_test = signals[:split], signals[split:]
                # Backtest on test data
                cumulative_returns, final_return = backtest(S1_test, S2_test, hedge_ratio, signals_test)
                # Store results
                results.append({
                    'pair': pair,
                    'half_life': hl,
                    'final_return': final_return,
                    'cumulative_returns': cumulative_returns
                })
                # Plot cumulative returns
                plt.figure(figsize=(10, 5))
                cumulative_returns.plot()
                plt.title(f'Cumulative Returns for Pair {pair}')
                plt.xlabel('Date')
                plt.ylabel('Cumulative Returns')
                plt.show()

    # Step 6: Select the best-performing pair
    if results:
        best_pair = max(results, key=lambda x: x['final_return'])
        print(f"Best-performing pair: {best_pair['pair']} with final return {best_pair['final_return']:.2f}")
    else:
        print("No suitable cointegrated pairs found.")
