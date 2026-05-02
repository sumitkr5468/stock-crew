from crewai import Crew, Process
from src.stock_crew.tasks import (
    fetch_price_task,
    fetch_fundamentals_task,
    fetch_sentiment_task,
    fetch_technical_task,
    analyse_stock_task
)


def run_stock_analysis(ticker: str, progress_callback=None):

    # 1. Define tasks in order
    price_task        = fetch_price_task(ticker)
    fundamentals_task = fetch_fundamentals_task(ticker)
    sentiment_task    = fetch_sentiment_task(ticker)
    technical_task    = fetch_technical_task(ticker)
    analysis_task     = analyse_stock_task(ticker)

    # 2. Define a closure to handle state transitions between tasks
    def make_callback(completed_stage, next_stage=None):
        def _callback(output):
            if progress_callback:
                # Mark current stage as complete
                progress_callback(completed_stage, "complete")
                # Mark the next stage as running
                if next_stage:
                    progress_callback(next_stage, "running")
        return _callback

    # 3. Attach the sequential callbacks to the Task objects
    price_task.callback        = make_callback("Market Data Specialist", "Fundamental Analyst")
    fundamentals_task.callback = make_callback("Fundamental Analyst", "Sentiment Analyst")
    sentiment_task.callback    = make_callback("Sentiment Analyst", "Technical Analyst")
    technical_task.callback    = make_callback("Technical Analyst", "Senior Investment Analyst")
    analysis_task.callback     = make_callback("Senior Investment Analyst", None)

    # 4. Assemble the crew
    crew = Crew(
        agents=[
            price_task.agent,
            fundamentals_task.agent,
            sentiment_task.agent,
            technical_task.agent,
            analysis_task.agent
        ],
        tasks=[
            price_task,
            fundamentals_task,
            sentiment_task,
            technical_task,
            analysis_task
        ],
        process=Process.sequential,
        verbose=True,
        max_rpm=10,            # max API calls per minute across all agents
    )

    # 5. Manually trigger the "running" state for the very first agent
    if progress_callback:
        progress_callback("Market Data Specialist", "running")

    # 6. Execute the Pipeline
    result = crew.kickoff()

    # 7. Token usage report
    print("\n" + "="*60)
    print("TOKEN USAGE REPORT")
    print("="*60)
    usage = crew.usage_metrics
    print(f"Total Input Tokens:      {usage.prompt_tokens:,}")
    print(f"Total Output Tokens:     {usage.completion_tokens:,}")
    print(f"Total Tokens:            {usage.total_tokens:,}")

    # Cost estimate
    input_cost  = (usage.prompt_tokens  / 1_000_000) * 0.15
    output_cost = (usage.completion_tokens / 1_000_000) * 0.60
    total_cost  = input_cost + output_cost
    print(f"\nEstimated Cost (GPT-4o-mini):")
    print(f"  Input:   ${input_cost:.4f}")
    print(f"  Output:  ${output_cost:.4f}")
    print(f"  Total:   ${total_cost:.4f}  (~₹{total_cost * 84:.2f})")
    print("="*60)

    return result