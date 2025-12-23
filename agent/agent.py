from agent.tools import get_market_data, get_news

def run_agent(symbol: str):
    market = get_market_data(symbol)
    news = get_news(symbol)

    return f"""
Crypto Research Report for {symbol}

Market:
- Price: ${market['price_usd']}
- RSI: {market['rsi']}
- MACD: {market['macd']}

News:
- {news[0]}
- {news[1]}
"""