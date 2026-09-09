import json

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
    # Constructs format like 'sep7.2026'
    month = target_date.strftime("%b").lower()
    return f"{month}{target_date.day}.{target_date.year}"


async def scrape_actual_values(target_date: datetime) -> Dict[str, Dict]:
    """Scrape all values (Actual, Forecast, Previous) from Forex Factory calendar page.
    Returns a dict mapping (currency|time|event) key to a dict with actual, forecast, previous."""
    date_str = format_date_for_url(target_date)
    url = f"https://www.forexfactory.com/calendar.php?day={date_str}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    scraped_data = {}
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Try multiple row selectors - Forex Factory may change class names
            row_selectors = [
                ".calendar__row.calendar__row--grey, .calendar__row.calendar__row--white",
                ".calendar__row",
                "tr.calendarRow",
                "tr[class*='calendar']"
            ]
            
            rows = []
            for selector in row_selectors:
                rows = soup.select(selector)
                if rows:
                    break
            
            if not rows:
                # Try finding any table rows
                table = soup.find("table")
                if table:
                    rows = table.find_all("tr")[1:]  # Skip header
            
            for row in rows:
                # Try multiple selectors for each field
                time_text = ""
                currency_text = ""
                event_text = ""
                actual_text = "N/A"
                forecast_text = "N/A"
                previous_text = "N/A"
                
                # Extract time
                for sel in [".calendar__time", "td.time", "td:has(span.time)"]:
                    elem = row.select_one(sel)
                    if elem:
                        time_text = elem.get_text(strip=True)
                        break
                
                # Extract currency
                for sel in [".calendar__currency", "td.currency", "td:has(span.currency)"]:
                    elem = row.select_one(sel)
                    if elem:
                        currency_text = elem.get_text(strip=True)
                        break
                
                # Extract event title
                for sel in [".calendar__event", "td.event", "td:has(a.event)"]:
                    elem = row.select_one(sel)
                    if elem:
                        event_text = elem.get_text(strip=True)
                        break
                
                # Extract actual value
                for sel in [".calendar__actual", "td.actual", "td:has(span.actual)"]:
                    elem = row.select_one(sel)
                    if elem:
                        actual_text = elem.get_text(strip=True) or "N/A"
                        break
                
                # Extract forecast value
                for sel in [".calendar__forecast", "td.forecast", "td:has(span.forecast)"]:
                    elem = row.select_one(sel)
                    if elem:
                        forecast_text = elem.get_text(strip=True) or "N/A"
                        break
                
                # Extract previous value
                for sel in [".calendar__previous", "td.previous", "td:has(span.previous)"]:
                    elem = row.select_one(sel)
                    if elem:
                        previous_text = elem.get_text(strip=True) or "N/A"
                        break
                
                if event_text:
                    # Create a unique key for matching with JSON data
                    key = f"{currency_text}|{time_text}|{event_text}"
                    scraped_data[key] = {
                        "actual": actual_text,
                        "forecast": forecast_text,
                        "previous": previous_text
                    }
                    
    except Exception as e:
        # If scraping fails, return empty dict (we'll fall back to JSON data)
        pass
    
    return scraped_data


# In-memory calendar cache
CALENDAR_CACHE = {"data": None, "timestamp": None}
CACHE_DURATION_HOURS = 1

async def fetch_calendar_events(target_date: datetime) -> List[Dict]:
    """Fetch and parse events from Forex Factory's official JSON API with caching."""
    global CALENDAR_CACHE
    
    now = datetime.now()
    use_cache = (
        CALENDAR_CACHE["data"] is not None
        and CALENDAR_CACHE["timestamp"] is not None
        and (now - CALENDAR_CACHE["timestamp"]) < timedelta(hours=CACHE_DURATION_HOURS)
    )

    data = None
    if use_cache:
        data = CALENDAR_CACHE["data"]
    else:
        # Endpoints to try (primary and CDN mirror)
        endpoints = [
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        for url in endpoints:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    response = await client.get(url, headers=headers, timeout=10.0)
                    response.raise_for_status()
                    data = response.json()
                    # Store in cache
                    CALENDAR_CACHE["data"] = data
                    CALENDAR_CACHE["timestamp"] = now
                    break
            except Exception:
                continue

    # If both endpoints fail and cache is empty, return an informative error
    if data is None:
        return [{
            "time": "N/A",
            "currency": "USD",
            "impact": "High",
            "event": "API Rate Limit (HTTP 429) hit. Please wait a few minutes before retrying.",
            "actual": "N/A",
            "forecast": "N/A",
            "previous": "N/A",
            "source_url": "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        }]

    events = []
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    # Scrape all values from the website to get Actual values
    scraped_data = await scrape_actual_values(target_date)

    for item in data:
        item_date_str = item.get("date", "")[:10]
        if item_date_str != target_date_str:
            continue

        time_str = "All Day"
        if "T" in item.get("date", ""):
            time_part = item["date"].split("T")[1][:5]
            if time_part != "00:00":
                time_str = time_part

        # Build event title with forecast/actual/previous - always include all three
        base_title = item.get("title", "N/A")
        json_forecast = item.get("forecast", "") or "N/A"
        json_previous = item.get("previous", "") or "N/A"
        json_actual = item.get("actual", "") or "N/A"
        
        # Try to get values from scraped data first, then fall back to JSON
        currency = item.get("country", "N/A")
        scraped_key = f"{currency}|{time_str}|{base_title}"
        scraped = scraped_data.get(scraped_key, {})
        
        actual_val = scraped.get("actual", json_actual)
        forecast_val = scraped.get("forecast", json_forecast)
        previous_val = scraped.get("previous", json_previous)
        
        # Always include all three in the title
        full_title = f"{base_title} (Forecast: {forecast_val}, Actual: {actual_val}, Previous: {previous_val})"
        
        events.append({
            "time": time_str,
            "currency": currency,
            "impact": item.get("impact", "N/A"),
            "event": full_title,
            "actual": actual_val,
            "forecast": forecast_val,
            "previous": previous_val,
            "source_url": "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        })

    return events


# --- Tool: Get economic calendar events for a specific day ---
@server.tool()
async def get_day_events(day: str = "today", currency: Optional[str] = None, impact: Optional[str] = None) -> str:
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
    
    # Call the JSON fetcher using the datetime object
    events = await fetch_calendar_events(target_date)
    
    filtered_events = []
    for event in events:
        if currency and event.get("currency", "").upper() not in [c.strip().upper() for c in currency.split(",")]:
            continue
        if impact and impact.lower() not in event.get("impact", "").lower():
            continue
        filtered_events.append(event)
    
    # Explicitly serialize the list to a valid JSON string
    return json.dumps(filtered_events)

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
    
    return json.dumps(news_items)

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
    
    return json.dumps({
        "title": title,
        "url": url,
        "content": content if content else "No content found",
        "date": date,
        "source": "Forex Factory"
    })

# --- Resource: Latest economic calendar (JSON) ---
@server.resource("calendar//today.json")
async def today_calendar_json() -> str:
    """Returns today's economic calendar as JSON."""
    import json
    # Use the new function name and pass "today"
    events = await get_day_events("today")
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
