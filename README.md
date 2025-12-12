# 🤖 BotTrader - Trading Bot Script Manager

A sleek web application to manage, run, and monitor your Python trading bots for Binance.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ Features

- **📝 Script Management** - Upload, edit, and delete Python trading bot scripts
- **▶️ Run/Stop Control** - Start and stop your bots with a single click
- **📊 Real-time Logs** - Monitor bot output in real-time
- **💾 Persistent Storage** - Scripts are saved to disk and persist across restarts
- **🎨 Modern UI** - Beautiful dark-themed trading terminal interface
- **📁 Drag & Drop** - Upload .py files by dragging them into the modal

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python app.py
```

### 3. Open in Browser

Navigate to [http://localhost:5000](http://localhost:5000)

## 📖 Usage

### Adding a New Bot

1. Click the **+** button in the sidebar
2. Enter a name for your bot
3. Either paste your Python code or drag & drop a `.py` file
4. Click **Add Bot**

### Running a Bot

1. Select a bot from the sidebar
2. Click the **Run** button
3. View real-time logs in the **Logs** tab

### Editing a Bot

1. Select the bot you want to edit
2. Make changes in the code editor
3. Press `Ctrl+S` or click **Save** to save changes

### Stopping a Bot

1. Select the running bot
2. Click the **Stop** button

### Deleting a Bot

1. Select the bot you want to remove
2. Click the **Delete** button
3. Confirm the deletion

## 📁 Project Structure

```
tradingwebsite/
├── app.py                 # Flask backend
├── database.py            # SQLite database for trade tracking
├── trade_reporter.py      # Helper module for logging trades
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── trades.db             # SQLite database (auto-created)
├── scripts/              # Uploaded bot scripts (auto-created, gitignored)
├── scripts_metadata.json # Script metadata (auto-created)
├── templates/
│   ├── index.html        # Main dashboard
│   ├── logs.html         # Logs page
│   ├── accounts.html     # Accounts management page
│   └── account_detail.html # Account detail page
└── static/
    ├── style.css         # Main stylesheet
    ├── script.js         # Dashboard JavaScript
    ├── logs.css/js       # Logs page styles/scripts
    └── accounts.css/js   # Accounts page styles/scripts
```

## 🔧 API Endpoints

### Scripts API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scripts` | Get all scripts |
| POST | `/api/scripts` | Upload a new script |
| GET | `/api/scripts/<id>` | Get script content |
| PUT | `/api/scripts/<id>` | Update script |
| DELETE | `/api/scripts/<id>` | Delete script |
| POST | `/api/scripts/<id>/run` | Run script |
| POST | `/api/scripts/<id>/stop` | Stop script |
| GET | `/api/scripts/<id>/logs` | Get script logs |

### Trades API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/trades` | Get all trades (filterable) |
| GET | `/api/trades/<id>` | Get specific trade |
| DELETE | `/api/trades/<id>` | Delete trade |
| GET | `/api/trades/stats` | Get trade statistics |

## 📝 Example Trading Bot

Here's a simple example bot template:

```python
from binance.client import Client
import time

# Your Binance API credentials
api_key = 'your_api_key_here'
api_secret = 'your_api_secret_here'

# Initialize client
client = Client(api_key, api_secret)

print("Bot started!")

while True:
    try:
        # Get current BTC price
        ticker = client.get_symbol_ticker(symbol="BTCUSDT")
        print(f"BTC/USDT: ${ticker['price']}")
        
        # Your trading logic here
        
        time.sleep(10)  # Check every 10 seconds
        
    except KeyboardInterrupt:
        print("Bot stopped by user")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
```

## 📊 Trade Tracking

BotTrader includes a built-in trade tracking system. Your bot scripts can log trades to an SQLite database, which are then viewable in the **Bots** and **Trades** pages.

### Using the Trade Reporter

Add this to your trading bot script (in the `scripts/` folder):

```python
# Add parent directory to path (required for scripts in scripts/ folder)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_reporter import TradeReporter

# Initialize with your script ID (the filename without .py)
reporter = TradeReporter(script_id="your_script_id")

# Register your bot (call once at startup)
reporter.register_bot("My Trading Bot", "BTCUSDT")

# When opening a trade
trade_id = reporter.open_trade(
    side="LONG",           # or "SHORT"
    leverage=50,           # leverage multiplier
    quantity=0.01,         # position size
    entry_price=97500.00,  # entry price
    commission=0.50        # entry commission/fee
)

# When closing a trade
result = reporter.close_trade(
    trade_id=trade_id,     # from open_trade()
    exit_price=98000.00,   # exit price
    commission=0.50,       # exit commission/fee
    reason="TP1"           # exit reason: TP, SL, SIGNAL, MANUAL
)

# Result contains:
# - pnl: Net profit/loss in USD
# - pnl_percent: Return on margin (accounts for leverage)
# - duration_seconds: Trade duration

print(f"Trade closed: ${result['pnl']:.2f} ({result['pnl_percent']:.1f}%)")
```

### Trade Reporter Methods

| Method | Description |
|--------|-------------|
| `register_bot(name, symbol)` | Register/update bot info |
| `open_trade(side, leverage, quantity, entry_price, commission)` | Log trade entry |
| `close_trade(trade_id, exit_price, commission, reason)` | Log trade exit with PnL |
| `has_open_trade()` | Check if there's an open trade |
| `get_stats()` | Get trading statistics |
| `get_recent_trades(limit)` | Get recent trades |

### Viewing Trades

- **Accounts Page** (`/accounts`): View all accounts with their statistics and trade history

## ⚠️ Important Notes

1. **API Keys**: Never commit your Binance API keys to version control
2. **Testing**: Always test scripts on Binance Testnet first
3. **Risk**: Trading scripts involve financial risk - use at your own discretion
4. **Permissions**: Use API keys with minimal required permissions

## 🛡️ Security Recommendations

- Store API keys in environment variables
- Use IP whitelisting on Binance
- Enable 2FA on your Binance account
- Start with small amounts when testing new strategies

## 📄 License

MIT License - feel free to use and modify for your trading needs!

---

**Happy Trading! 📈**

