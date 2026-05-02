from crewai import Task
from src.stock_crew.agents import market_data_agent, fundamentals_agent, analyst_agent, sentiment_agent, technical_agent

def fetch_price_task(ticker: str):
    return Task(
        description=f"""
        Fetch the latest stock price and trading data for {ticker}.
        Use the 'Get stock price data' tool to retrieve:
        - Current price
        - Previous close
        - Day high and low
        - Volume
        - 52 week high and low
        - Market cap
        
        Present the data clearly and note any significant observations 
        e.g. if the stock is near its 52 week high or low.
        """,
        expected_output=f"""
        A clear summary of current price data for {ticker} with 
        key observations about trading levels and market cap.
        """,
        agent=market_data_agent()
    )


def fetch_fundamentals_task(ticker: str):
    return Task(
        description=f"""
        Fetch and analyse the fundamental data for {ticker}.
        Use the 'Get stock fundamentals' tool to retrieve:
        - P/E ratio and EPS
        - Revenue and profit margins
        - Return on equity
        - Debt to equity ratio
        - Dividend yield
        - Book value
        
        Interpret each metric — is the P/E high or low for the sector? 
        Is the debt level concerning? Is ROE strong?
        """,
        expected_output=f"""
        A fundamental analysis summary for {ticker} that interprets 
        each metric and flags strengths and weaknesses.
        """,
        agent=fundamentals_agent()
    )


def analyse_stock_task(ticker: str):
    return Task(
        description=f"""
        Using the price data and fundamental analysis already gathered for {ticker},
        produce a concise investment research report.
        
        Your report must include:
        1. One paragraph summary of the stock's current position
        2. Bull case — top 2 to 3 reasons to buy
        3. Bear case — top 2 to 3 risks or concerns
        4. Overall recommendation — Buy, Hold, or Avoid with clear reasoning
        5. Key metrics snapshot — price, P/E, market cap, 52 week range
        """,
        expected_output=f"""
        A structured investment research report for {ticker} with 
        bull case, bear case, and a clear Buy / Hold / Avoid recommendation.
        """,
        agent=analyst_agent()
    )



def fetch_sentiment_task(ticker: str):
    return Task(
        description=f"""
        Search for and analyse the 5 most recent news articles about {ticker}.
        
        For each article note:
        - What the news is about
        - Whether it is positive, negative or neutral for the stock
        - Why it matters for investors
        
        Then give an overall sentiment score:
        - Bullish — majority of news is positive
        - Neutral — mixed signals
        - Bearish — majority of news is negative or concerning
        
        Use the company name in your search, not just the ticker code.
        For example search for 'Deepak Fertilisers' not just 'DEEPAKFERT.NS'
        """,
        expected_output=f"""
        A sentiment summary for {ticker} covering recent news headlines,
        individual article assessments, and an overall Bullish / Neutral / Bearish 
        sentiment score with reasoning. Include specific examples from recent news to support your assessment.
        Give two or three most relevant news headlines with a one line summary and link and sentiment for each.
        """,
        agent=sentiment_agent()
    )

def fetch_technical_task(ticker: str):
    return Task(
        description=f"""
        Compute and interpret the full technical analysis for {ticker}.
        Use the 'Get technical analysis' tool to retrieve indicators.
        
        Interpret the following as a system — look for confluence:
        - Moving Averages: is the stock in an uptrend or downtrend?
        - RSI: is the stock overbought, oversold, or neutral?
        - MACD: is momentum bullish or bearish? Any recent crossovers?
        - Bollinger Bands: is the stock near the upper or lower band?
        
        Then give an overall technical verdict:
        - Bullish Setup — multiple indicators pointing up
        - Bearish Setup — multiple indicators pointing down
        - Mixed / Consolidating — no clear directional signal
        
        Always explain what a non-technical investor should take away.
        """,
        expected_output=f"""
        A technical analysis summary for {ticker} covering all four 
        indicator groups with individual interpretations and an overall 
        Bullish / Bearish / Mixed verdict with plain English explanation.
        """,
        agent=technical_agent()
    )