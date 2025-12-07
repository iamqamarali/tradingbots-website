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
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── scripts/              # Uploaded bot scripts (auto-created)
├── scripts_metadata.json # Script metadata (auto-created)
├── templates/
│   └── index.html        # Main HTML template
└── static/
    ├── style.css         # Stylesheet
    └── script.js         # Frontend JavaScript
```

## 🔧 API Endpoints

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

## ⚠️ Important Notes

1. **API Keys**: Never commit your Binance API keys to version control
2. **Testing**: Always test bots on Binance Testnet first
3. **Risk**: Trading bots involve financial risk - use at your own discretion
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

