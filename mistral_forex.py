#!/usr/bin/env python3
import os
import asyncio
import requests
import json
from dotenv import load_dotenv
from mcp import Client, StdioServerParameters

load_dotenv()  # Load environment variables from .env file

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Forex explanation prompt for beginners
FOREX_EXPLANATION_PROMPT = """
Explain this forex concept in 2-3 simple sentences using plain English. 
Avoid jargon. Focus on:
1. What it is
2. Why it matters for currency prices
3. Simple real-world analogy if possible
"""

# Forex event explanation prompt (for individual events)
FOREX_EVENT_PROMPT = """
Explain this economic event for a forex beginner. Be concise (2-3 sentences max).
Format:
- What this event measures
- How it typically affects currency prices
- Simple real-world comparison
"""

# Global MCP client instance
mcp_client = None


async def call_mcp_tool(name, args={}):
    """Call your Forex Factory MCP server using the client API"""
    global mcp_client

    if mcp_client is None:
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "forex_factory_mcp.py"]
        )
        mcp_client = Client(server=server_params)
        await mcp_client.__aenter__()

    result = await mcp_client.call_tool(name, args)
    
    # Extract and parse the JSON string from the CallToolResult
    try:
        return json.loads(result.content[0].text)
    except (json.JSONDecodeError, AttributeError):
        return result.content[0].text if hasattr(result, 'content') else result


async def close_mcp_client():
    """Close the MCP client connection"""
    global mcp_client
    if mcp_client is not None:
        await mcp_client.__aexit__(None, None, None)
        mcp_client = None


def ask_mistral(content, model="mistral-tiny", is_event=False):
    """Ask Mistral to explain forex data using the appropriate prompt"""
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Use event-specific prompt for individual events
    prompt = FOREX_EVENT_PROMPT if is_event else FOREX_EXPLANATION_PROMPT
    
    data = {
        "model": model,
        "messages": [{"role": "user", "content": f"{prompt}\n\n{content}"}],
        "temperature": 0.7
    }
    response = requests.post(MISTRAL_URL, headers=headers, json=data)
    return response.json()["choices"][0]["message"]["content"]


async def main():
    print("\n=== Mistral + Forex Factory Terminal ===")
    print("Type 'events [day]' for events (e.g., 'events today', 'events monday'), 'news [query]' to search, 'article [id]' for specific article, 'exit' to quit")

    try:
        while True:
            user_input = input("\n> ").strip().lower()

            if user_input == "exit":
                break

            elif user_input.startswith("events "):
                day = user_input[7:].strip() or "today"
                events = await call_mcp_tool("get_day_events", {"day": day, "currency": "USD,EUR"})
                
                # Print each event with its details
                if isinstance(events, list):
                    if len(events) == 0:
                        print("\nNo events found for that day.")
                    else:
                        for event in events:
                            title = event.get('event', 'N/A')
                            forecast = event.get('forecast', 'N/A')
                            actual = event.get('actual', 'N/A')
                            impact = event.get('impact', 'N/A')
                            time = event.get('time', 'N/A')
                            currency = event.get('currency', 'N/A')
                            
                            print(f"\n--- {title} ---")
                            print(f"Currency: {currency} | Time: {time} | Impact: {impact}")
                            if forecast != 'N/A':
                                print(f"Forecast: {forecast}")
                            if actual != 'N/A':
                                print(f"Actual: {actual}")
                            
                            # Get explanation for this specific event
                            event_content = f"Event: {title}\nCurrency: {currency}\nForecast: {forecast}\nActual: {actual}\nImpact: {impact}"
                            explanation = ask_mistral(event_content, is_event=True)
                            print(f"Explanation: {explanation}")
                else:
                    print(f"\nUnexpected response format. Raw server output:\n{events}")

            elif user_input == "events":
                # Default to today
                events = await call_mcp_tool("get_day_events", {"day": "today", "currency": "USD,EUR"})
                
                # Print each event with its details
                if isinstance(events, list):
                    for event in events:
                        title = event.get('event', 'N/A')
                        forecast = event.get('forecast', 'N/A')
                        actual = event.get('actual', 'N/A')
                        previous = event.get('previous', 'N/A')
                        impact = event.get('impact', 'N/A')
                        time = event.get('time', 'N/A')
                        currency = event.get('currency', 'N/A')
                        
                        print(f"\n--- {title} ---")
                        print(f"Currency: {currency} | Time: {time} | Impact: {impact}")
                        if forecast != 'N/A':
                            print(f"Forecast: {forecast}")
                        if actual != 'N/A':
                            print(f"Actual: {actual}")
                        if previous != 'N/A':
                            print(f"Previous: {previous}")
                        
                        # Get explanation for this specific event
                        event_content = f"Event: {title}\nCurrency: {currency}\nForecast: {forecast}\nActual: {actual}\nPrevious: {previous}\nImpact: {impact}"
                        explanation = ask_mistral(event_content, is_event=True)
                        print(f"Explanation: {explanation}")
                else:
                    print("\nNo events found for that day.")

            elif user_input.startswith("news "):
                query = user_input[5:]
                news = await call_mcp_tool("search_forex_factory_news", {"query": query, "limit": 3})
                explanation = ask_mistral(news)
                print("\n" + explanation)

            elif user_input.startswith("article "):
                article_id = user_input[8:]  # Extract the ID/slug
                article = await call_mcp_tool("get_news_article", {"news_id": article_id})
                
                # Handle both dict and string responses
                if isinstance(article, dict):
                    content = f"Title: {article.get('title', 'N/A')}\n\n{article.get('content', 'N/A')}"
                else:
                    content = f"Article data: {article}"
                
                explanation = ask_mistral(content)
                print("\n" + explanation)

            else:
                # Direct chat with Mistral about forex
                response = ask_mistral(user_input)
                print("\n" + response)
    
    finally:
        await close_mcp_client()


if __name__ == "__main__":
    asyncio.run(main())
