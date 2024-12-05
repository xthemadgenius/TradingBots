//@version=5
indicator("Enhanced BASE Chain Long Algo", overlay=true)

// Inputs
len_rsi = input.int(14, title="RSI Length")
rsi_oversold = input.int(30, title="RSI Oversold Level")
len_ema = input.int(50, title="EMA Length")
len_sma = input.int(200, title="SMA Length")
vol_filter = input.bool(true, title="Enable Volume Filter")
vol_threshold = input.float(1.5, title="Volume Multiplier", step=0.1)
atr_len = input.int(14, title="ATR Length")
sl_atr_mult = input.float(1.5, title="Stop Loss ATR Multiplier", step=0.1)
tp_atr_mult = input.float(2.5, title="Take Profit ATR Multiplier", step=0.1)

// Calculations
rsi = ta.rsi(close, len_rsi)
ema = ta.ema(close, len_ema)
sma = ta.sma(close, len_sma)
atr = ta.atr(atr_len)

// Volume Filter
volume_avg = ta.sma(volume, len_ema)
volume_condition = volume > (volume_avg * vol_threshold) or not vol_filter

// Entry Condition
long_condition = (rsi < rsi_oversold) and (ema > sma) and (close > ema) and volume_condition

// Stop Loss and Take Profit Levels
long_stop_loss = close - (atr * sl_atr_mult)
long_take_profit = close + (atr * tp_atr_mult)

// Plotting
plot(ema, color=color.green, linewidth=1, title="EMA")
plot(sma, color=color.red, linewidth=1, title="SMA")
hline(rsi_oversold, "RSI Oversold", color=color.blue, linestyle=hline.style_dotted)
bgcolor(long_condition ? color.new(color.green, 90) : na, title="Long Signal Background")

// Plot Stop Loss and Take Profit
plot(long_condition ? long_stop_loss : na, color=color.red, style=plot.style_circles, title="Stop Loss")
plot(long_condition ? long_take_profit : na, color=color.green, style=plot.style_circles, title="Take Profit")

// Alerts
if (long_condition)
    alert("Long Entry Signal Detected! Check Stop Loss and Take Profit levels.", alert.freq_once_per_bar)

// Optional Exit Signal Visualization
exit_signal = ta.cross(close, ema)
bgcolor(exit_signal ? color.new(color.red, 90) : na, title="Exit Signal Background")

// Commentary Overlay
label.new(bar_index, high, text="Long Entry" if long_condition else na, style=label.style_label_up, color=color.new(color.green, 80))
label.new(bar_index, low, text="Exit Signal" if exit_signal else na, style=label.style_label_down, color=color.new(color.red, 80))
