#!/usr/bin/env python3
"""
Forex Factory Chat UI with Markdown Rendering
Uses MCP to fetch data and Rich for beautiful terminal output.
"""

import os
import asyncio
from dotenv import load_dotenv
from mcp import Client, StdioServerParameters
import requests
import json

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich import box

load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Forex explanation prompts
FOREX_EXPLANATION_PROMPT = """
Explain this forex concept in 2-3 simple sentences using plain English. 
Avoid jargon. Focus on:
1. What it is
2. Why it matters for currency prices
3. Simple real-world analogy if possible
"""

FOREX_EVENT_PROMPT = """
Explain this economic event for a forex beginner. Be concise (2-3 sentences max).
Format:
- What this event measures
- How it typically affects currency prices
- Simple real-world comparison
"""

console = Console()
mcp_client = None


async def call_mcp_tool(name, args={}):
    """Call the Forex Factory MCP server."""
    global mcp_client

    if mcp_client is None:
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "forex_factory_mcp.py"]
        )
        mcp_client = Client(server=server_params)
        await mcp_client.__aenter__()

    result = await mcp_client.call_tool(name, args)
    
    try:
        return json.loads(result.content[0].text)
    except (json.JSONDecodeError, AttributeError):
        return result.content[0].text if hasattr(result, 'content') else result


async def close_mcp_client():
    """Close the MCP client connection."""
    global mcp_client
    if mcp_client is not None:
        await mcp_client.__aexit__(None, None, None)
        mcp_client = None


def ask_mistral(content, model="mistral-tiny", is_event=False):
    """Ask Mistral to explain forex data."""
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = FOREX_EVENT_PROMPT if is_event else FOREX_EXPLANATION_PROMPT
    
    data = {
        "model": model,
        "messages": [{"role": "user", "content": f"{prompt}\n\n{content}"}],
        "temperature": 0.7
    }
    response = requests.post(MISTRAL_URL, headers=headers, json=data)
    return response.json()["choices"][0]["message"]["content"]


def render_markdown(text):
    """Render markdown text beautifully in the terminal."""
    console.print(Panel.fit(Markdown(text), border_style="blue", box=box.ROUNDED))


def render_events(events):
    """Render events list with markdown formatting."""
    if not events:
        console.print("[yellow]No events found for that day.[/yellow]")
        return
    
    markdown = "### Economic Calendar Events\n\n"
    for event in events:
        title = event.get('event', 'N/A')
        currency = event.get('currency', 'N/A')
        time = event.get('time', 'N/A')
        impact = event.get('impact', 'N/A')
        forecast = event.get('forecast', 'N/A')
        actual = event.get('actual', 'N/A')
        previous = event.get('previous', 'N/A')
        
        markdown += f"---\n\n"
        markdown += f"**{title}**\n\n"
        markdown += f"> 💱 Currency: {currency} | ⏰ Time: {time} | ⚡ Impact: {impact}\n\n"
        
        # Always include forecast, actual, previous if they exist in the data
        if forecast != 'N/A' and forecast:
            markdown += f"📊 Forecast: `{forecast}`\n\n"
        if actual != 'N/A' and actual:
            markdown += f"✅ Actual: `{actual}`\n\n"
        if previous != 'N/A' and previous:
            markdown += f"📜 Previous: `{previous}`\n\n"
        
        # Get explanation
        event_content = f"Event: {title}\nCurrency: {currency}\nForecast: {forecast}\nActual: {actual}\nImpact: {impact}"
        explanation = ask_mistral(event_content, is_event=True)
        markdown += f"💡 *{explanation}*\n\n"
    
    render_markdown(markdown)


def render_news(news):
    """Render news results with markdown formatting."""
    if not news:
        console.print("[yellow]No news found.[/yellow]")
        return
    
    markdown = "### Forex News\n\n"
    for item in news:
        title = item.get('title', 'N/A')
        summary = item.get('summary', 'N/A')
        url = item.get('url', '#')
        date = item.get('date', 'N/A')
        
        markdown += f"- **[{title}]({url})**\n"
        markdown += f"  > {summary}\n"
        markdown += f"  *{date}*\n\n"
    
    explanation = ask_mistral(str(news))
    markdown += f"---\n\n{explanation}"
    
    render_markdown(markdown)


def render_article(article):
    """Render article with markdown formatting."""
    if isinstance(article, dict):
        title = article.get('title', 'N/A')
        content = article.get('content', 'N/A')
        url = article.get('url', '#')
        date = article.get('date', 'N/A')
        
        markdown = f"# {title}\n\n"
        markdown += f"> [View on Forex Factory]({url}) | {date}\n\n"
        markdown += f"{content}\n"
    else:
        markdown = str(article)
    
    explanation = ask_mistral(markdown)
    markdown += f"\n---\n\n{explanation}"
    
    render_markdown(markdown)


async def main():
    console.print(Panel.fit(
        "[bold blue]💬 Forex Factory Chat UI[/bold blue]\n\n"
        "[dim]Powered by Mistral AI & MCP[/dim]",
        border_style="blue",
        box=box.DOUBLE
    ))
    
    console.print("\n[bold]Commands:[/bold]")
    console.print("  - [cyan]events [day][/cyan] - Show events (e.g., 'events today', 'events thursday')")
    console.print("  - [cyan]news [query][/cyan] - Search news")
    console.print("  - [cyan]article [id][/cyan] - Get specific article")
    console.print("  - [cyan]exit[/cyan] - Quit\n")

    try:
        while True:
            user_input = console.input("[bold blue]>[/bold blue] ").strip().lower()

            if user_input == "exit":
                break

            elif user_input.startswith("events "):
                day = user_input[7:].strip() or "today"
                console.print(f"[dim]Fetching events for {day}...[/dim]")
                events = await call_mcp_tool("get_day_events", {"day": day, "currency": "USD,EUR"})
                
                if isinstance(events, list):
                    render_events(events)
                elif isinstance(events, str):
                    try:
                        render_events(json.loads(events))
                    except:
                        render_markdown(events)
                else:
                    render_markdown(str(events))

            elif user_input == "events":
                console.print("[dim]Fetching today's events...[/dim]")
                events = await call_mcp_tool("get_day_events", {"day": "today", "currency": "USD,EUR"})
                if isinstance(events, list):
                    render_events(events)
                elif isinstance(events, str):
                    try:
                        render_events(json.loads(events))
                    except:
                        render_markdown(events)
                else:
                    render_markdown(str(events))

            elif user_input.startswith("news "):
                query = user_input[5:].strip()
                if query:
                    console.print(f"[dim]Searching news for '{query}'...[/dim]")
                    news = await call_mcp_tool("search_forex_factory_news", {"query": query, "limit": 5})
                    if isinstance(news, list):
                        render_news(news)
                    elif isinstance(news, str):
                        try:
                            render_news(json.loads(news))
                        except:
                            render_markdown(news)
                    else:
                        render_markdown(str(news))
                else:
                    console.print("[yellow]Please provide a search query.[/yellow]")

            elif user_input.startswith("article "):
                article_id = user_input[8:].strip()
                if article_id:
                    console.print(f"[dim]Fetching article {article_id}...[/dim]")
                    article = await call_mcp_tool("get_news_article", {"news_id": article_id})
                    render_article(article)
                else:
                    console.print("[yellow]Please provide an article ID.[/yellow]")

            else:
                # Direct chat with Mistral
                if user_input:
                    console.print("[dim]Asking Mistral...[/dim]")
                    response = ask_mistral(user_input)
                    render_markdown(response)

    finally:
        await close_mcp_client()
        console.print("\n[yellow]Goodbye![/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
