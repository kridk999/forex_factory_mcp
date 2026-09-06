from mcp.server import MCPServer
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
import os

# Initialize MCP server
server = MCPServer("forex-factory-mcp")

# --- Tool: Get today's economic calendar events ---
@server.tool()
async def get_today_events(currency: Optional[str] = None, impact: Optional[str] = None) -> List[Dict]:
    """
    Fetch today's economic calendar events from Forex Factory.
    
    Args:
        currency: Filter by currency (e.g., 'USD', 'EUR', 'GBP'). If None, returns all.
        impact: Filter by impact level ('high', 'medium', 'low'). If None, returns all.
    
    Returns:
        List of event dictionaries with keys: time, currency, impact, event, actual, forecast, previous.
    """
    url = "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    
    # Parse the calendar table (simplified example)
    events = []
    rows = soup.select(".calendar__row.calendar__row--grey")
    
    for row in rows:
        time = row.select_one(".calendar__time").get_text(strip=True) if row.select_one(".calendar__time") else "N/A"
        currency = row.select_one(".calendar__currency").get_text(strip=True) if row.select_one(".calendar__currency") else "N/A"
        impact = row.select_one(".calendar__impact span")["title"] if row.select_one(".calendar__impact span") else "N/A"
        event = row.select_one(".calendar__event").get_text(strip=True) if row.select_one(".calendar__event") else "N/A"
        actual = row.select_one(".calendar__actual").get_text(strip=True) if row.select_one(".calendar__actual") else "N/A"
        forecast = row.select_one(".calendar__forecast").get_text(strip=True) if row.select_one(".calendar__forecast") else "N/A"
        previous = row.select_one(".calendar__previous").get_text(strip=True) if row.select_one(".calendar__previous") else "N/A"
        
        # Apply filters
        if currency and currency.upper() not in currency:
            continue
        if impact and impact.lower() not in impact.lower():
            continue
            
        events.append({
            "time": time,
            "currency": currency,
            "impact": impact,
            "event": event,
            "actual": actual,
            "forecast": forecast,
            "previous": previous,
            "source_url": url
        })
    
    return events

# --- Tool: Search Forex Factory news ---
@server.tool()
async def search_forex_factory_news(query: str, limit: int = 5) -> List[Dict]:
    """
    Search Forex Factory news for a given query.
    
    Args:
        query: Search term (e.g., 'FOMC', 'CPI', 'ECB').
        limit: Maximum number of results to return.
    
    Returns:
        List of news item dictionaries with keys: title, url, summary, date.
    """
    url = f"https://www.forexfactory.com/news?search={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    
    news_items = []
    articles = soup.select(".news-article")[:limit]
    
    for article in articles:
        title = article.select_one(".news-article__title").get_text(strip=True)
        article_url = article.select_one("a")["href"]
        if not article_url.startswith("http"):
            article_url = f"https://www.forexfactory.com{article_url}"
        summary = article.select_one(".news-article__excerpt").get_text(strip=True)
        date = article.select_one(".news-article__date").get_text(strip=True)
        
        news_items.append({
            "title": title,
            "url": article_url,
            "summary": summary,
            "date": date
        })
    
    return news_items

# --- Tool: Get specific news article by ID/slug ---
@server.tool()
async def get_news_article(news_id: str) -> Dict:
    """
    Fetch a specific Forex Factory news article by its ID or URL slug.
    
    Args:
        news_id: The news ID or URL slug (e.g., '1416551-gold-prices-coin-flip-lasted-a-day')
                 Can also be just the ID number (e.g., '1416551')
    
    Returns:
        Dictionary with title, url, full content, date, and source.
    """
    # Handle both full slug and just ID
    if '-' not in news_id:
        url = f"https://www.forexfactory.com/news/{news_id}"
    else:
        url = f"https://www.forexfactory.com/news/{news_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    
    article = soup.find("article") or soup
    title_elem = article.select_one("h1") or article.select_one(".news-article__title")
    title = title_elem.get_text(strip=True) if title_elem else "N/A"
    
    # Try to get the main content
    content_elem = (article.select_one(".news-article__content") or
                   article.select_one(".article-content") or
                   article)
    
    content_text = content_elem.get_text(strip=True, separator="\n") if hasattr(content_elem, 'get_text') else str(content_elem)
    
    # Get date
    date_elem = article.select_one(".news-article__date") or article.select_one("time")
    date = date_elem.get_text(strip=True) if date_elem else "N/A"
    
    return {
        "title": title,
        "url": url,
        "content": content_text,
        "date": date,
        "source": "Forex Factory"
    }

# --- Resource: Latest economic calendar (JSON) ---
@server.resource("calendar//today.json")
async def today_calendar_json() -> str:
    """Returns today's economic calendar as JSON."""
    import json
    events = await get_today_events()
    return json.dumps(events, indent=2)

# --- Resource: Latest news (JSON) ---
@server.resource("news//latest.json")
async def latest_news_json() -> str:
    """Returns the latest Forex Factory news as JSON."""
    import json
    news = await search_forex_factory_news("forex", limit=10)
    return json.dumps(news, indent=2)

# Run the server
if __name__ == "__main__":
    print("Forex Factory MCP server starting...")
    print("Available tools: get_today_events, search_forex_factory_news, get_news_article")
    print("Available resources: calendar//today.json, news//latest.json")
    print("Waiting for MCP client connections...")
    server.run()
