# Importing all the essential Python libraries
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
%matplotlib inline
sns.set_style('whitegrid')

# Importing data reader from pandas_datareader
from pandas_datareader.data import DataReader

# Importing datetime for setting start and end date of the stock market dataset
from datetime import datetime

# Setting the Start and End date for Stock Market Analysis
end = datetime.now()
start = datetime(end.year - 1, end.month, end.day)

# Importing Apple Stock Prices
AAPL = DataReader('AAPL', 'yahoo', start, end)

# Some Basic info about the Apple Stock
print(AAPL.describe())

# Plotting Adjusted Closing price for Apple Stock
AAPL['Adj Close'].plot(legend=True, figsize=(10, 4))
plt.title('Adjusted Closing Price of Apple Stock')
plt.show()

# Plotting the total volume of stock being traded each day
AAPL['Volume'].plot(legend=True, figsize=(10, 4))
plt.title('Daily Trading Volume of Apple Stock')
plt.show()

# Calculating Moving average for 10, 20 and 50 days of the stock price
ma_day = [10, 20, 50]

for ma in ma_day:
    column_name = f"MA for {ma} days"
    AAPL[column_name] = AAPL['Adj Close'].rolling(window=ma).mean()

# Plotting the moving averages
AAPL[['Adj Close', 'MA for 10 days', 'MA for 20 days', 'MA for 50 days']].plot(figsize=(12, 6))
plt.title('Moving Averages of Apple Stock')
plt.show()

# Plotting Daily returns as a function of Percent change in Adjusted Close value
AAPL['Daily Return'] = AAPL['Adj Close'].pct_change()
AAPL['Daily Return'].plot(legend=True, figsize=(10, 4))
plt.title('Daily Return of Apple Stock')
plt.show()

# Plotting the average daily returns of the stock
sns.histplot(AAPL['Daily Return'].dropna(), bins=100, kde=True)
plt.title('Distribution of Daily Returns')
plt.show()

# Risk Analysis -- Comparing the Risk vs Expected returns
rets = AAPL['Daily Return'].dropna()

plt.scatter(rets.mean(), rets.std(), s=50)
plt.xlabel('Expected Returns')
plt.ylabel('Risk')
plt.title('Risk vs Expected Returns')
plt.show()

# Visualizing the Value at Risk
sns.histplot(AAPL['Daily Return'].dropna(), bins=100, kde=True)
plt.title('Value at Risk (VaR) Analysis')
plt.show()

# Using Quantiles to calculate the numerical risk of the stock
VaR = AAPL['Daily Return'].quantile(0.05)
print(f"Value at Risk (5% quantile): {VaR}")

## Monte Carlo Simulation
days = 365
dt = 1 / days
mu = rets.mean()
sigma = rets.std()

# Defining the Monte Carlo Simulation Function
def stock_monte_carlo(start_price, days, mu, sigma):
    price = np.zeros(days)
    price[0] = start_price
    
    for t in range(1, days):
        # Random Shock
        rand = np.random.normal()
        price[t] = price[t - 1] * np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * rand * np.sqrt(dt))
        
    return price

# Running the Monte Carlo simulation 100 times
start_price = AAPL['Adj Close'][-1]

plt.figure(figsize=(10, 6))
for run in range(100):
    plt.plot(stock_monte_carlo(start_price, days, mu, sigma))
plt.xlabel('Days')
plt.ylabel('Price')
plt.title('Monte Carlo Simulation for Apple Stock')
plt.show()

# Analyzing the Monte Carlo Simulation for 10,000 simulations
runs = 10000
simulations = np.zeros(runs)

for run in range(runs):
    simulations[run] = stock_monte_carlo(start_price, days, mu, sigma)[-1]
    
# 1 percent empirical quantile or 99% Confidence Interval
q = np.percentile(simulations, 1)

# Plotting the final Risk Analysis plot using Monte Carlo Simulation
plt.figure(figsize=(10, 6))
plt.hist(simulations, bins=200)
plt.figtext(0.6, 0.8, f"Start price: ${start_price:.2f}")
# Mean ending price
plt.figtext(0.6, 0.7, f"Mean final price: ${simulations.mean():.2f}")
# Variance of the price (within 99% confidence interval)
plt.figtext(0.6, 0.6, f"VaR(0.99): ${start_price - q:.2f}")
# Display 1% quantile
plt.figtext(0.15, 0.6, f"q(0.99): ${q:.2f}")
# Plot a line at the 1% quantile result
plt.axvline(x=q, linewidth=4, color='r')
# Title
plt.title(f"Final price distribution for Apple Stock after {days} days", weight='bold')
plt.show()
