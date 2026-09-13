import json
import re
from mcp.server import MCPServer
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os

# Initialize MCP server
server = MCPServer("forex-factory-mcp")

def normalize_str(s: str) -> str:
    """Removes all non-alphanumeric characters and lowercases to guarantee exact matching."""
    if not s: return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()

def get_date_from_string(day_name: str) -> datetime:
    """Convert day name to next upcoming date."""
    day_name = day_name.lower()
    today = datetime.now()
    
    day_map = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6, 'today': today.weekday(),
        'tomorrow': (today.weekday() + 1) % 7
    }
    
    if day_name in day_map:
        target_weekday = day_map[day_name]
    else:
        return today
        
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0 and day_name != 'today':
        days_ahead = 7
        
    return today + timedelta(days=days_ahead)

def format_date_for_url(target_date: datetime) -> str:
    """Format date for Forex Factory calendar URL."""
    month = target_date.strftime("%b").lower()
    return f"{month}{target_date.day}.{target_date.year}"

async def scrape_actual_values(target_date: datetime) -> Dict[str, List[Dict]]:
    """Scrape all values (Actual, Forecast, Previous) from Forex Factory calendar page.
    Returns a dict mapping (currency|event) key to a list of dicts with actual, forecast, previous."""
    date_str = format_date_for_url(target_date)
    url = f"https://www.forexfactory.com/calendar?day={date_str}"
    
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }
    
    scraped_data = {}
    
    try:
        # Using curl_cffi with Chrome impersonation to bypass TLS fingerprinting
        async with AsyncSession(impersonate="chrome") as client:
            response = await client.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Robust row matching
            rows = soup.select("tr.calendar__row")
            if not rows:
                rows = soup.select("tr[data-eventid]")
            if not rows:
                table = soup.find("table")
                if table:
                    rows = table.find_all("tr")[1:]
            
            for row in rows:
                currency_elem = row.select_one("td.calendar__currency, td.currency")
                if not currency_elem: continue
                currency_text = currency_elem.get_text(strip=True)
                if not currency_text: continue
                    
                event_elem = row.select_one("td.calendar__event, td.event")
                event_text = event_elem.get_text(strip=True) if event_elem else ""
                
                actual_elem = row.select_one("td.calendar__actual, td.actual")
                actual_text = actual_elem.get_text(strip=True) if actual_elem else ""
                if not actual_text: actual_text = "N/A"
                
                forecast_elem = row.select_one("td.calendar__forecast, td.forecast")
                forecast_text = forecast_elem.get_text(strip=True) if forecast_elem else ""
                if not forecast_text: forecast_text = "N/A"
                
                previous_elem = row.select_one("td.calendar__previous, td.previous")
                previous_text = previous_elem.get_text(strip=True) if previous_elem else ""
                if not previous_text: previous_text = "N/A"
                
                if event_text:
                    key = f"{normalize_str(currency_text)}|{normalize_str(event_text)}"
                    if key not in scraped_data:
                        scraped_data[key] = []
                    
                    scraped_data[key].append({
                        "actual": actual_text,
                        "forecast": forecast_text,
                        "previous": previous_text
                    })
                    
    except Exception:
        pass
        
    return scraped_data

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
        endpoints = [
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"
        ]
        for url in endpoints:
            try:
                async with AsyncSession(impersonate="chrome") as client:
                    response = await client.get(url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    CALENDAR_CACHE["data"] = data
                    CALENDAR_CACHE["timestamp"] = now
                    break
            except Exception:
                continue

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

        base_title = item.get("title", "N/A")
        json_forecast = item.get("forecast", "") or "N/A"
        json_previous = item.get("previous", "") or "N/A"
        json_actual = item.get("actual", "") or "N/A"
        
        currency = item.get("country", "N/A")
        
        # Look up using normalized robust currency|event key
        scraped_key = f"{normalize_str(currency)}|{normalize_str(base_title)}"
        scraped_list = scraped_data.get(scraped_key, [])
        
        scraped = {}
        if len(scraped_list) > 0:
            scraped = scraped_list.pop(0)
            
        actual_val = scraped.get("actual") if scraped.get("actual") not in [None, "", "N/A"] else json_actual
        forecast_val = scraped.get("forecast") if scraped.get("forecast") not in [None, "", "N/A"] else json_forecast
        previous_val = scraped.get("previous") if scraped.get("previous") not in [None, "", "N/A"] else json_previous
        
        if not actual_val: actual_val = "N/A"
        if not forecast_val: forecast_val = "N/A"
        if not previous_val: previous_val = "N/A"
        
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

@server.tool()
async def get_day_events(day: str = "today", currency: Optional[str] = None, impact: Optional[str] = None) -> str:
    """Fetch economic calendar events for a specific day from Forex Factory."""
    if day.lower() == "today":
        target_date = datetime.now()
    elif day.lower() == "tomorrow":
        target_date = datetime.now() + timedelta(days=1)
    else:
        try:
            target_date = get_date_from_string(day)
        except:
            try:
                target_date = datetime.strptime(day, "%Y-%m-%d")
            except:
                target_date = datetime.now()
                
    events = await fetch_calendar_events(target_date)
    
    filtered_events = []
    for event in events:
        if currency and event.get("currency", "").upper() not in [c.strip().upper() for c in currency.split(",")]:
            continue
        if impact and impact.lower() not in event.get("impact", "").lower():
            continue
        filtered_events.append(event)
        
    return json.dumps(filtered_events)

@server.tool()
async def search_forex_factory_news(query: str, limit: int = 5) -> List[Dict]:
    """Search Forex Factory news for a given query."""
    url = f"https://www.forexfactory.com/news?search={query}"
    
    async with AsyncSession(impersonate="chrome") as client:
        response = await client.get(url)
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

@server.tool()
async def get_news_article(news_id: str) -> Dict:
    """Fetch a specific Forex Factory news article by its ID or URL slug."""
    if '-' in news_id:
        url = f"https://www.forexfactory.com/news/{news_id}"
    else:
        url = f"https://www.forexfactory.com/news/{news_id}"
        
    async with AsyncSession(impersonate="chrome") as client:
        response = await client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
    title = soup.select_one("h1") or soup.select_one(".news-title")
    title = title.get_text(strip=True) if title else "No title found"
    
    content_selectors = [
        ".news-content", ".article-body", ".post-content",
        "article", ".content", "div[itemprop='articleBody']",
        ".news-article__content",
    ]
    
    content = ""
    for selector in content_selectors:
        elem = soup.select_one(selector)
        if elem:
            content = elem.get_text(strip=True, separator="\n")
            break
            
    if not content:
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

@server.resource("calendar://today.json")
async def today_calendar_json() -> str:
    """Returns today's economic calendar as JSON."""
    events = await get_day_events("today")
    return json.dumps(json.loads(events), indent=2)

@server.resource("news://latest.json")
async def latest_news_json() -> str:
    """Returns the latest Forex Factory news as JSON."""
    news = await search_forex_factory_news("forex", limit=10)
    return json.dumps(json.loads(news), indent=2)

if __name__ == "__main__":
    print("Forex Factory MCP server starting...")
    print("Available tools: get_day_events, search_forex_factory_news, get_news_article")
    print("Available resources: calendar://today.json, news://latest.json")
    print("Waiting for MCP client connections...")
    server.run()