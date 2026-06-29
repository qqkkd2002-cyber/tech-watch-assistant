import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import ssl
import certifi
from typing import Callable, Dict, List
import datetime

def fetch_xml(url: str) -> str:
    """Fetches raw content from a URL using urllib."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching feed from {url}: {e}")
        return ""

def parse_feed(xml_data: str) -> List[Dict[str, str]]:
    """Parses RSS or Atom XML and returns a list of dictionaries with standard keys:
    title, link, description, date
    """
    if not xml_data:
        return []
        
    entries = []
    try:
        root = ET.fromstring(xml_data)
        
        # Check if Atom feed
        is_atom = False
        if 'feed' in root.tag or root.tag.endswith('feed'):
            is_atom = True
            
        if is_atom:
            # Atom namespaces can vary, find entry elements ignoring namespace
            # We can find all elements by searching tags ending with 'entry'
            for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry') or root.findall('.//entry') or root.findall('{http://www.w3.org/2005/Atom}entry'):
                title_el = entry.find('.//{http://www.w3.org/2005/Atom}title') or entry.find('title')
                title = title_el.text if title_el is not None else "No Title"
                
                link_el = entry.find('.//{http://www.w3.org/2005/Atom}link') or entry.find('link')
                link = ""
                if link_el is not None:
                    link = link_el.attrib.get('href', '')
                    if not link and link_el.text:
                        link = link_el.text.strip()
                        
                desc_el = entry.find('.//{http://www.w3.org/2005/Atom}summary') or entry.find('.//{http://www.w3.org/2005/Atom}content') or entry.find('summary') or entry.find('content')
                description = desc_el.text if desc_el is not None else ""
                
                date_el = entry.find('.//{http://www.w3.org/2005/Atom}updated') or entry.find('.//{http://www.w3.org/2005/Atom}published') or entry.find('updated') or entry.find('published')
                date_str = date_el.text if date_el is not None else ""
                
                entries.append({
                    "title": title.strip(),
                    "link": link.strip(),
                    "description": description.strip() if description else "",
                    "date": date_str.strip(),
                    "source": "",
                })
        else:
            # Standard RSS
            for item in root.findall('.//item'):
                title_el = item.find('title')
                title = title_el.text if title_el is not None else "No Title"
                
                link_el = item.find('link')
                link = link_el.text if link_el is not None else ""
                
                desc_el = item.find('description')
                description = desc_el.text if desc_el is not None else ""
                
                date_el = item.find('pubDate')
                date_str = date_el.text if date_el is not None else ""

                source_el = item.find('source')
                source = source_el.text if source_el is not None and source_el.text else ""
                
                entries.append({
                    "title": title.strip(),
                    "link": link.strip(),
                    "description": description.strip() if description else "",
                    "date": date_str.strip(),
                    "source": source.strip(),
                })
                
    except Exception as e:
        print(f"Error parsing XML: {e}")
        
    return entries

def get_competitor_updates(feed_url: str) -> List[Dict[str, str]]:
    """Fetches updates from a competitor's release RSS feed."""
    xml_data = fetch_xml(feed_url)
    return parse_feed(xml_data)

def search_google_news(keyword: str, recency_days: int = 2) -> List[Dict[str, str]]:
    """Searches Google News RSS for articles matching a specific keyword."""
    query = f"{keyword} when:{recency_days}d" if recency_days else keyword
    encoded_keyword = urllib.parse.quote(query)
    # Search in Korean, region South Korea, and ask Google News for recent items.
    url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"
    
    xml_data = fetch_xml(url)
    all_news = parse_feed(xml_data)
    
    # Return top 10 news items
    return all_news[:10]


TREND_NEWS_PROVIDERS: Dict[str, Callable[[str, int], List[Dict[str, str]]]] = {
    "google_news": search_google_news,
}


def search_trend_news(keyword: str, recency_days: int = 2, provider: str = "google_news") -> List[Dict[str, str]]:
    """Fetch trend items through a replaceable provider boundary."""
    fetcher = TREND_NEWS_PROVIDERS.get(provider)
    if not fetcher:
        print(f"Unknown trend news provider '{provider}'.")
        return []
    return fetcher(keyword, recency_days)

if __name__ == "__main__":
    # Test feed parser
    print("Testing GitLab release RSS feed...")
    gitlab_feed = "https://about.gitlab.com/releases/categories/releases.xml"
    updates = get_competitor_updates(gitlab_feed)
    print(f"Fetched {len(updates)} updates from GitLab.")
    if updates:
        print(f"Latest Update: {updates[0]['title']} ({updates[0]['link']})")
        
    print("\nTesting Google News search...")
    news = search_google_news("GitLab")
    print(f"Fetched {len(news)} news articles about GitLab.")
    if news:
        print(f"Latest News: {news[0]['title']} ({news[0]['link']})")
