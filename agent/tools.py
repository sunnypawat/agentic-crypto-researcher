import requests

def get_market_data(symbol: str):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": symbol.lower(), "vs_currencies": "usd"}
    price = requests.get(url, params=params).json()[symbol.lower()]["usd"]

    return {
        "price_usd": price,
        "rsi": 65,
        "macd": "bullish"
    }

def get_news(symbol: str):
    return [
        f"{symbol} sees increased institutional interest",
        f"Analysts discuss {symbol} outlook"
    ]

