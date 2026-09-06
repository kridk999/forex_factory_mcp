from mcp.server import MCPServer
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os

# Initialize MCP server
server = MCPServer("forex-factory-mcp")


def get_date_from_string(day_name: str) -> datetime:
    """Convert day name to next upcoming date."""
    day_name = day_name.lower()
    today = datetime.now()
    
    day_map = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6,
        'today': today.weekday(),
        'tomorrow': (today.weekday() + 1) % 7
    }
    
    if day_name in day_map:
        target_weekday = day_map[day_name]
    else:
        return today  # Default to today
    
    # Find next occurrence of the target weekday
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0 and day_name != 'today':
        days_ahead = 7  # Next week
    
    return today + timedelta(days=days_ahead)


def format_date_for_url(target_date: datetime) -> str:
    """Format date for Forex Factory calendar URL."""
    return target_date.strftime("%Y-%m-%d")


async def fetch_calendar_events(url: str) -> List[Dict]:
    """Fetch and parse events from Forex Factory calendar URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    
    events = []
    rows = soup.select(".calendar__row.calendar__row--grey")
    
    for row in rows:
        time = row.select_one(".calendar__time").get_text(strip=True) if row.select_one(".calendar__time") else "N/A"
        currency = row.select_one(".calendar__currency").get_text(strip=True) if row.select_one(".calendar__currency") else "N/A"
        impact_elem = row.select_one(".calendar__impact span")
        impact = impact_elem["title"] if impact_elem else "N/A"
        event = row.select_one(".calendar__event").get_text(strip=True) if row.select_one(".calendar__event") else "N/A"
        actual = row.select_one(".calendar__actual").get_text(strip=True) if row.select_one(".calendar__actual") else "N/A"
        forecast = row.select_one(".calendar__forecast").get_text(strip=True) if row.select_one(".calendar__forecast") else "N/A"
        previous = row.select_one(".calendar__previous").get_text(strip=True) if row.select_one(".calendar__previous") else "N/A"
        
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


# --- Tool: Get economic calendar events for a specific day ---
@server.tool()
async def get_day_events(day: str = "today", currency: Optional[str] = None, impact: Optional[str] = None) -> List[Dict]:
    """
    Fetch economic calendar events for a specific day from Forex Factory.
    
    Args:
        day: Day name ('today', 'tomorrow', 'monday', 'tuesday', etc.) or date in YYYY-MM-DD format.
        currency: Filter by currency (e.g., 'USD', 'EUR', 'GBP'). If None, returns all.
        impact: Filter by impact level ('high', 'medium', 'low'). If None, returns all.
    
    Returns:
        List of event dictionaries with keys: time, currency, impact, event, actual, forecast, previous.
    """
    # Parse the day parameter
    if day.lower() == "today":
        target_date = datetime.now()
    elif day.lower() == "tomorrow":
        target_date = datetime.now() + timedelta(days=1)
    else:
        # Try to parse as a day name
        try:
            target_date = get_date_from_string(day)
        except:
            # Try to parse as a date string (YYYY-MM-DD)
            try:
                target_date = datetime.strptime(day, "%Y-%m-%d")
            except:
                target_date = datetime.now()
    
    # Build the URL with the target date
    formatted_date = format_date_for_url(target_date)
    url = f"https://www.forexfactory.com/calendar?day={formatted_date}"
    
    events = await fetch_calendar_events(url)
    
    # Apply filters
    filtered_events = []
    for event in events:
        if currency and event.get("currency", "").upper() != currency.upper():
            continue
        if impact and impact.lower() not in event.get("impact", "").lower():
            continue
        filtered_events.append(event)
    
    return filtered_events

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
    if '-' in news_id:
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
    
    # Forex Factory article structure
    title = soup.select_one("h1") or soup.select_one(".news-title")
    title = title.get_text(strip=True) if title else "No title found"
    
    # Try multiple selectors for content
    content_selectors = [
        ".news-content",
        ".article-body",
        ".post-content",
        "article",
        ".content",
        "div[itemprop='articleBody']",
        ".news-article__content",
    ]
    
    content = ""
    for selector in content_selectors:
        elem = soup.select_one(selector)
        if elem:
            content = elem.get_text(strip=True, separator="\n")
            break
    
    if not content:
        # Fallback: get all paragraphs
        paragraphs = soup.find_all('p')
        content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    
    date_elem = soup.select_one("time") or soup.select_one(".date") or soup.select_one(".news-article__date")
    date = date_elem.get_text(strip=True) if date_elem else "No date"
    
    return {
        "title": title,
        "url": url,
        "content": content if content else "No content found",
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
    print("Available tools: get_day_events, search_forex_factory_news, get_news_article")
    print("Available resources: calendar//today.json, news//latest.json")
    print("Waiting for MCP client connections...")
    server.run()
