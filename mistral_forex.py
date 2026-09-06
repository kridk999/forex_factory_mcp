#!/usr/bin/env python3
import os
import subprocess
import requests
import json
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

def call_mcp_tool(name, args={}):
    """Call your Forex Factory MCP server"""
    cmd = ["mcp", "call", name]
    for k, v in args.items():
        cmd.extend(["--arg", k, str(v)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout.strip()
    
    # Try to find and parse JSON in the output
    # MCP CLI might wrap JSON in other text
    if "{" in output and "}" in output:
        # Try to extract JSON from output
        start = output.rfind("{")
        end = output.rfind("}") + 1
        json_str = output[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # If no JSON found, return raw output
    return output

def ask_mistral(prompt, model="mistral-tiny"):
    """Ask Mistral to explain forex data"""
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    response = requests.post(MISTRAL_URL, headers=headers, json=data)
    return response.json()["choices"][0]["message"]["content"]

def main():
    print("\n=== Mistral + Forex Factory Terminal ===")
    print("Type 'events' for today's events, 'news [query]' to search, 'article [id]' for specific article, 'exit' to quit")

    while True:
        user_input = input("\n> ").strip().lower()

        if user_input == "exit":
            break

        elif user_input == "events":
            events = call_mcp_tool("get_today_events", {"currency": "USD"})
            explanation = ask_mistral(f"Explain these forex economic events to a beginner trader:\n\n{events}")
            print("\n" + explanation)

        elif user_input.startswith("news "):
            query = user_input[5:]
            news = call_mcp_tool("search_forex_factory_news", {"query": query, "limit": 3})
            explanation = ask_mistral(f"Summarize this forex news for a beginner:\n\n{news}")
            print("\n" + explanation)

        elif user_input.startswith("article "):
            article_id = user_input[8:]  # Extract the ID/slug
            article = call_mcp_tool("get_news_article", {"news_id": article_id})
            
            # Debug: print what we got
            print(f"DEBUG: article type = {type(article)}")
            print(f"DEBUG: article = {article[:200] if isinstance(article, str) else article}")
            
            # Handle both dict and string responses
            if isinstance(article, dict):
                content = f"Title: {article.get('title', 'N/A')}\n\n{article.get('content', 'N/A')}"
            else:
                content = f"Article data: {article}"
            
            explanation = ask_mistral(
                f"Summarize and explain this forex news article for a beginner:\n\n{content}"
            )
            print("\n" + explanation)

        else:
            # Direct chat with Mistral about forex
            response = ask_mistral(f"Forex trading question: {user_input}")
            print("\n" + response)

if __name__ == "__main__":
    main()