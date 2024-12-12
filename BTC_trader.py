import ccxt
import pandas as pd
import numpy as np
import time
import smtplib
from email.mime.text import MIMEText

# Configuration: Replace with your API keys and exchange details
API_KEY = 'your_api_key'
API_SECRET = 'your_api_secret'
EXCHANGE_NAME = 'binance'
EXTERNAL_WALLET = 'your_external_wallet_address'

SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'
LIMIT = 100
RISK_PERCENT = 0.01

SHORT_MA = 7
LONG_MA = 25
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

BALANCE_THRESHOLD = 1000  # USDT balance threshold for auto-withdrawal
RESERVE_BALANCE = 500  # Amount to keep in exchange wallet

# Email settings
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_USER = 'your_email@gmail.com'
EMAIL_PASS = 'your_email_password'
EMAIL_RECIPIENT = 'recipient_email@gmail.com'

# Initialize the exchange
exchange = getattr(ccxt, EXCHANGE_NAME)({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
})

def fetch_data():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_indicators(df):
    df['SMA_Short'] = df['close'].rolling(window=SHORT_MA).mean()
    df['SMA_Long'] = df['close'].rolling(window=LONG_MA).mean()
    delta = df['close'].diff(1)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=RSI_PERIOD).mean()
    avg_loss = pd.Series(loss).rolling(window=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def check_signal(df):
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    if last_row['SMA_Short'] > last_row['SMA_Long'] and prev_row['SMA_Short'] <= prev_row['SMA_Long']:
        if last_row['RSI'] < RSI_OVERSOLD:
            return 'buy'
    if last_row['SMA_Short'] < last_row['SMA_Long'] and prev_row['SMA_Short'] >= prev_row['SMA_Long']:
        if last_row['RSI'] > RSI_OVERBOUGHT:
            return 'sell'
    return None

def calculate_position_size(balance, price, risk_percent):
    risk_amount = balance * risk_percent
    stop_loss_distance = price * 0.01
    position_size = risk_amount / stop_loss_distance
    return position_size

def place_order(signal, price):
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['free']['USDT']
        position_size = calculate_position_size(usdt_balance, price, RISK_PERCENT)

        if signal == 'buy':
            order = exchange.create_market_buy_order(SYMBOL, position_size)
            print(f"Buy order placed: {order}")
        elif signal == 'sell':
            btc_balance = balance['free']['BTC']
            if btc_balance > 0:
                order = exchange.create_market_sell_order(SYMBOL, btc_balance)
                print(f"Sell order placed: {order}")
    except Exception as e:
        print(f"Error placing order: {e}")

def withdraw_to_external_wallet():
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['free']['USDT']

        if usdt_balance > BALANCE_THRESHOLD:
            amount_to_withdraw = usdt_balance - RESERVE_BALANCE
            withdrawal = exchange.withdraw('USDT', amount_to_withdraw, EXTERNAL_WALLET)
            print(f"Funds withdrawn: {withdrawal}")
            send_email("Withdrawal Notification", f"Successfully withdrew {amount_to_withdraw} USDT to {EXTERNAL_WALLET}.")
    except Exception as e:
        print(f"Error withdrawing funds: {e}")

def send_email(subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_RECIPIENT

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, EMAIL_RECIPIENT, msg.as_string())
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"Error sending email: {e}")

def main():
    print("Starting trading bot with wallet management...")
    while True:
        df = fetch_data()
        if df is not None:
            df = calculate_indicators(df)
            signal = check_signal(df)
            ticker = exchange.fetch_ticker(SYMBOL)
            price = ticker['last']
            if signal:
                print(f"Signal detected: {signal}")
                place_order(signal, price)
        withdraw_to_external_wallet()  # Check and withdraw excess funds
        time.sleep(60)

if __name__ == '__main__':
    main()
