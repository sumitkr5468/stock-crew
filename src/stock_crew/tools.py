from crewai.tools import tool
import yfinance as yf

@tool("Get stock price data")
def get_stock_price(ticker: str) -> str:
    """
    Fetches the latest stock price and key trading data for a given ticker symbol.
    Use NSE format for Indian stocks e.g. RELIANCE.NS, TCS.NS, HDFCBANK.NS
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        price       = info.get("currentPrice") or info.get("regularMarketPrice", "N/A")
        prev_close  = info.get("previousClose", "N/A")
        day_high    = info.get("dayHigh", "N/A")
        day_low     = info.get("dayLow", "N/A")
        volume      = info.get("volume", "N/A")
        week_52_high = info.get("fiftyTwoWeekHigh", "N/A")
        week_52_low  = info.get("fiftyTwoWeekLow", "N/A")
        market_cap  = info.get("marketCap", "N/A")

        return f"""
Stock: {ticker}
Current Price:   {price}
Previous Close:  {prev_close}
Day High:        {day_high}
Day Low:         {day_low}
Volume:          {volume}
52-Week High:    {week_52_high}
52-Week Low:     {week_52_low}
Market Cap:      {market_cap}
        """
    except Exception as e:
        return f"Error fetching data for {ticker}: {str(e)}"


@tool("Get stock fundamentals")
def get_stock_fundamentals(ticker: str) -> str:
    """
    Fetches key fundamental data for a given ticker symbol.
    Includes P/E ratio, EPS, revenue, profit margins and dividend yield.
    Use NSE format for Indian stocks e.g. RELIANCE.NS, TCS.NS
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        pe_ratio        = info.get("trailingPE", "N/A")
        eps             = info.get("trailingEps", "N/A")
        revenue         = info.get("totalRevenue", "N/A")
        profit_margin   = info.get("profitMargins", "N/A")
        roe             = info.get("returnOnEquity", "N/A")
        debt_to_equity  = info.get("debtToEquity", "N/A")
        dividend_yield  = info.get("dividendYield", "N/A")
        book_value      = info.get("bookValue", "N/A")

        return f"""
Stock: {ticker}
P/E Ratio:        {pe_ratio}
EPS:              {eps}
Total Revenue:    {revenue}
Profit Margin:    {profit_margin}
Return on Equity: {roe}
Debt to Equity:   {debt_to_equity}
Dividend Yield:   {dividend_yield}
Book Value:       {book_value}
        """
    except Exception as e:
        return f"Error fetching fundamentals for {ticker}: {str(e)}"
    
import os
import requests

@tool("Get recent stock news")
def get_stock_news(ticker: str) -> str:
    """
    Searches for recent news articles about a stock.
    Input should be the company name or ticker e.g. Deepak Fertilisers, TCS, Reliance.
    Returns recent headlines and summaries to assess market sentiment.
    """
    try:
        api_key = os.environ.get("SERPER_API_KEY")
        
        url = "https://google.serper.dev/news"
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": f"{ticker} stock news India",
            "num": 5,
            "gl": "in",
            "hl": "en"
        }

        response = requests.post(url, headers=headers, json=payload)
        data = response.json()

        news_items = data.get("news", [])
        if not news_items:
            return f"No recent news found for {ticker}"

        result = f"Recent news for {ticker}:\n\n"
        for i, item in enumerate(news_items, 1):
            title   = item.get("title", "No title")
            source  = item.get("source", "Unknown source")
            date    = item.get("date", "Unknown date")
            snippet = item.get("snippet", "No summary available")
            result += f"{i}. {title}\n"
            result += f"   Source: {source} | Date: {date}\n"
            result += f"   {snippet}\n\n"

        return result

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"
    
import pandas_ta as ta

@tool("Get technical analysis")
def get_technical_analysis(ticker: str) -> str:
    """
    Computes technical indicators for a given stock ticker.
    Returns RSI, MACD, Bollinger Bands, and Moving Averages.
    Use NSE format for Indian stocks e.g. RELIANCE.NS, TCS.NS
    """
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")

        if df.empty:
            return f"No price history found for {ticker}"

        # Moving averages
        df["MA20"]  = ta.sma(df["Close"], length=20)
        df["MA50"]  = ta.sma(df["Close"], length=50)
        df["MA200"] = ta.sma(df["Close"], length=200)

        # RSI
        df["RSI"] = ta.rsi(df["Close"], length=14)

        # MACD
        macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
        df["MACD"]        = macd["MACD_12_26_9"]
        df["MACD_Signal"] = macd["MACDs_12_26_9"]
        df["MACD_Hist"]   = macd["MACDh_12_26_9"]

        # Bollinger Bands
        bbands = ta.bbands(df["Close"], length=20, std=2)
        bb_cols = [c for c in bbands.columns if c.startswith("BBU")]
        bbl_cols = [c for c in bbands.columns if c.startswith("BBL")]
        bbm_cols = [c for c in bbands.columns if c.startswith("BBM")]
        df["BB_Upper"]  = bbands[bb_cols[0]]
        df["BB_Middle"] = bbands[bbm_cols[0]]
        df["BB_Lower"]  = bbands[bbl_cols[0]]

        # Drop rows with NaN and get latest
        df = df.dropna(subset=["MA20", "MA50", "RSI", "MACD", "BB_Upper"])
        if df.empty:
            return f"Not enough data to compute indicators for {ticker}"

        latest = df.iloc[-1]
        price  = latest["Close"]

        # Safe value extraction
        rsi_value  = latest["RSI"]
        macd_value = latest["MACD"]
        macd_sig   = latest["MACD_Signal"]
        macd_hist  = latest["MACD_Hist"]
        ma20       = latest["MA20"]
        ma50       = latest["MA50"]
        ma200      = latest.get("MA200")
        bb_upper   = latest["BB_Upper"]
        bb_lower   = latest["BB_Lower"]
        bb_middle  = latest["BB_Middle"]

        # Interpret RSI
        if rsi_value >= 70:
            rsi_signal = "Overbought — potential reversal downward"
        elif rsi_value <= 30:
            rsi_signal = "Oversold — potential reversal upward"
        else:
            rsi_signal = "Neutral"

        # Interpret MACD
        if macd_value > macd_sig:
            macd_interpretation = "Bullish — MACD above signal line"
        else:
            macd_interpretation = "Bearish — MACD below signal line"

        # Interpret Bollinger Bands
        if price >= bb_upper:
            bb_interpretation = "Price at upper band — overbought territory"
        elif price <= bb_lower:
            bb_interpretation = "Price at lower band — oversold territory"
        else:
            bb_position = ((price - bb_lower) / (bb_upper - bb_lower)) * 100
            bb_interpretation = f"Price within bands — {bb_position:.0f}% from lower to upper band"

        # Interpret Moving Averages
        if ma200 and not isinstance(ma200, float.__class__):
            ma200 = None

        if ma200 and price > ma20 > ma50 > ma200:
            ma_interpretation = "Strong uptrend — price above all moving averages"
        elif price > ma50:
            ma_interpretation = "Uptrend — price above 50-day MA"
        elif price < ma50:
            ma_interpretation = "Downtrend — price below 50-day MA"
        else:
            ma_interpretation = "Mixed — no clear trend"

        ma200_display = f"₹{ma200:.2f}" if ma200 else "N/A (insufficient data)"

        return f"""
Technical Analysis for {ticker}:

Current Price: ₹{price:.2f}

Moving Averages:
  20-day MA:  ₹{ma20:.2f}
  50-day MA:  ₹{ma50:.2f}
  200-day MA: {ma200_display}
  Interpretation: {ma_interpretation}

RSI (14):
  Value: {rsi_value:.2f}
  Signal: {rsi_signal}

MACD (12/26/9):
  MACD Line:    {macd_value:.4f}
  Signal Line:  {macd_sig:.4f}
  Histogram:    {macd_hist:.4f}
  Interpretation: {macd_interpretation}

Bollinger Bands (20, 2):
  Upper Band:  ₹{bb_upper:.2f}
  Middle Band: ₹{bb_middle:.2f}
  Lower Band:  ₹{bb_lower:.2f}
  Interpretation: {bb_interpretation}
        """

    except Exception as e:
        return f"Error computing technical analysis for {ticker}: {str(e)}"