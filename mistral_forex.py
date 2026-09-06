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

# Global MCP client instance
mcp_client = None


async def call_mcp_tool(name, args={}):
    """Call your Forex Factory MCP server using the client API"""
    global mcp_client
    
    if mcp_client is None:
        # Use StdioServerParameters to start the server
        # command must be a string, not a list
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "forex_factory_mcp.py"]
        )
        mcp_client = Client(server=server_params)
        await mcp_client.__aenter__()
    
    result = await mcp_client.call_tool(name, args)
    return result


async def close_mcp_client():
    """Close the MCP client connection"""
    global mcp_client
    if mcp_client is not None:
        await mcp_client.__aexit__(None, None, None)
        mcp_client = None


def ask_mistral(content, model="mistral-tiny"):
    """Ask Mistral to explain forex data using the consistent prompt"""
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": f"{FOREX_EXPLANATION_PROMPT}\n\n{content}"}],
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
                events = await call_mcp_tool("get_day_events", {"day": day, "currency": "USD"})
                explanation = ask_mistral(events)
                print("\n" + explanation)
            
            elif user_input == "events":
                # Default to today
                events = await call_mcp_tool("get_day_events", {"day": "today", "currency": "USD"})
                explanation = ask_mistral(events)
                print("\n" + explanation)

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
