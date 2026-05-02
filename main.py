import sys
import os
from dotenv import load_dotenv

# Load API keys from .env file
load_dotenv()

# Add src to path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from src.stock_crew.crew import run_stock_analysis


if __name__ == "__main__":
    ticker = input("Enter stock ticker (e.g. RELIANCE.NS, TCS.NS): ").strip()
    
    if not ticker:
        print("No ticker entered. Exiting.")
        sys.exit(1)

    print(f"\nStarting analysis for {ticker}...\n")
    result = run_stock_analysis(ticker)
    
    print("\n" + "="*60)
    print("FINAL REPORT")
    print("="*60)
    print(result)