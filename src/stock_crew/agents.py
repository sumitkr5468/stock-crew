from crewai import Agent, LLM
from src.stock_crew.tools import get_stock_price, get_stock_fundamentals, get_stock_news, get_technical_analysis

# Define the LLM once, reuse across all agents
llm = LLM(model="gpt-4o-mini")


def market_data_agent():
    return Agent(
        role="Market Data Specialist",
        goal="Fetch accurate and up to date stock price data for the given ticker",
        backstory="""You are an expert in financial markets with years of experience 
        tracking stock prices and trading data. You know how to read market signals 
        and present price data clearly. You always use NSE format for Indian stocks 
        e.g. RELIANCE.NS""",
        tools=[get_stock_price],
        llm=llm,
        verbose=True,
        max_iter=3,           # max attempts before giving up
        max_retry_limit=2     # max retries on tool failure
    )


def fundamentals_agent():
    return Agent(
        role="Fundamental Analysis Specialist",
        goal="Analyse the financial health and valuation of a stock using key fundamental metrics",
        backstory="""You are a seasoned equity analyst with deep expertise in fundamental 
        analysis. You have evaluated hundreds of companies across sectors. You focus on 
        P/E ratios, earnings quality, return on equity, debt levels, and profit margins 
        to assess whether a stock is fairly valued, undervalued, or overvalued.""",
        tools=[get_stock_fundamentals],
        llm=llm,
        verbose=True,
        max_iter=3,
        max_retry_limit=2
    )


def sentiment_agent():
    return Agent(
        role="Market Sentiment Analyst",
        goal="Analyse recent news and assess market sentiment for a given stock",
        backstory="""You are a specialist in market sentiment analysis with deep 
        experience tracking news flow, analyst commentary, and corporate announcements 
        for Indian listed companies. You read between the lines — a routine quarterly 
        result can hide margin pressure, a management interview can signal strategy shifts. 
        You always assess whether recent news is net positive, net negative, or neutral 
        for the stock and explain why.""",
        tools=[get_stock_news],
        llm=llm,
        verbose=True,
        max_iter=3,
        max_retry_limit=2
    )


def technical_agent():
    return Agent(
        role="Technical Analysis Specialist",
        goal="Analyse price charts and technical indicators to identify trends, momentum and entry points",
        backstory="""You are an expert technical analyst with 15 years of experience 
        reading charts for Indian equity markets. You are highly skilled at interpreting 
        RSI, MACD, Bollinger Bands, and moving averages together as a system — not in 
        isolation. You always look for confluence — when multiple indicators agree, 
        the signal is stronger. You translate technical signals into plain English 
        that a fundamental investor can understand.
        If the tool returns an error, report the error clearly and stop — do not retry.""",
        tools=[get_technical_analysis],
        llm=llm,
        verbose=True,
        max_iter=2,           # technical tool either works or it doesn't
        max_retry_limit=1
    )


def analyst_agent():
    return Agent(
        role="Senior Investment Analyst",
        goal="Synthesise price data, fundamental analysis, news sentiment and technical analysis into a clear investment thesis",
        backstory="""You are a senior investment analyst at a top asset management firm. 
        You take inputs from market data specialists, fundamental analysts, sentiment 
        analysts and technical analysts and produce concise, actionable research reports. 
        You always present a bull case, a bear case, and a clear overall recommendation 
        with reasoning. If technical analysis is unavailable, note it and proceed with 
        the remaining data. You should show topmost relevant news headlines with a one line summary and sentiment for each.
        You should also show as summary of technical indicators with a one line interpretation for each.""",
        tools=[],
        llm=llm,
        verbose=True,
        max_iter=3,
        max_retry_limit=1
    )