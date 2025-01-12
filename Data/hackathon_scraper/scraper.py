import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import datetime
import concurrent.futures
from tqdm import tqdm  # For progress bar
import csv

def generate_urls(event: str = "bangkok", total_pages: int = 23) -> list:
    """Generate URLs for a specific ETHGlobal event showcase"""
    base_url = "https://ethglobal.com/showcase"
    return [f"{base_url}?events={event}&page={page}" for page in range(1, total_pages + 1)]

def get_project_links(url: str) -> list:
    """Extract project links from a single page"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        project_links = []
        for project in soup.find_all('a', href=True):
            if '/showcase/' in project['href']:
                full_url = f"https://ethglobal.com{project['href']}"
                project_links.append(full_url)
        
        return project_links
        
    except requests.RequestException as e:
        print(f"Error fetching page {url}: {e}")
        return []

def scrape_event(urls: list, output_file: str) -> pd.DataFrame:
    """Scrape all project links from given URLs and save to CSV"""
    all_project_links = []
    
    for url in urls:
        print(f"Scraping: {url}")
        project_links = get_project_links(url)
        all_project_links.extend(project_links)
        print(f"Found {len(project_links)} projects on this page")
    
    df = pd.DataFrame(all_project_links, columns=['project_url'])
    
    # Create results directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df.to_csv(output_file, index=False)
    
    print(f"\nTotal projects found: {len(all_project_links)}")
    return df

def read_project_urls(csv_path: str) -> list:
    """Read project URLs from CSV file"""
    df = pd.read_csv(csv_path)
    return df['project_url'].tolist()

def scrape_project_details(url: str, output_file: str) -> dict:
    """Scrape details from a single project page"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        current_year = datetime.now().year
        
        # Extract Project Name (h1 tag)
        project_name = soup.find('h1').get_text(strip=True) if soup.find('h1') else 'N/A'
        
        # Extract Event Name and Year
        event_section = soup.find(text="Created At")
        event_name = 'N/A'
        event_year = current_year
        
        if event_section:
            event_div = event_section.find_next()
            if event_div:
                event_name = event_div.get_text(strip=True)
                # Add current year if no year in event name
                if not any(str(year) in event_name for year in range(2020, current_year + 1)):
                    event_year = current_year
                else:
                    # Extract year from event name if present
                    for year in range(2020, current_year + 1):
                        if str(year) in event_name:
                            event_year = year
                            event_name = event_name.replace(str(year), '').strip()
                            break
        
        # Extract Short Description (text right after project name)
        short_desc = None
        h1_tag = soup.find('h1')
        if h1_tag:
            next_p = h1_tag.find_next('p')
            if next_p:
                short_desc = next_p.get_text(strip=True)
        short_desc = short_desc if short_desc else 'N/A'
        
        # Extract Full Description (under "Project Description")
        full_description = 'N/A'
        desc_header = soup.find(text="Project Description")
        if desc_header:
            desc_content = []
            current = desc_header.find_next()
            while current and current.name != 'h3':  # Stop at next h3 header
                if current.name == 'p':
                    desc_content.append(current.get_text(strip=True))
                current = current.find_next()
            full_description = ' '.join(desc_content) if desc_content else 'N/A'
        
        # Extract Demo & Source URLs
        demo_url = 'N/A'
        source_code_url = 'N/A'
        for link in soup.find_all('a', href=True):
            if 'Live Demo' in link.get_text():
                demo_url = link['href']
            elif 'Source Code' in link.get_text():
                source_code_url = link['href']
        
        # Extract Tech Stack (under "How it's Made")
        tech_stack = 'N/A'
        tech_section = soup.find(text="How it's Made")
        if tech_section:
            tech_content = []
            current = tech_section.find_next()
            while current and current.name != 'h2':  # Stop at next h2 header
                if current.name == 'p':
                    tech_content.append(current.get_text(strip=True))
                current = current.find_next()
            tech_stack = ' '.join(tech_content) if tech_content else 'N/A'
        
        # Extract Prizes (under "Winner of")
        prizes = []
        prizes_section = soup.find(text="Winner of")
        if prizes_section:
            prize_elements = prizes_section.find_next().find_all('h4')
            prizes = [prize.get_text(strip=True) for prize in prize_elements]
        
        return {
            'project_url': url,
            'project_name': project_name,
            'event_name': event_name,
            'event_year': event_year,
            'short_description': short_desc,
            'full_description': full_description,
            'demo_url': demo_url,
            'source_code_url': source_code_url,
            'tech_stack': tech_stack,
            'prizes': prizes if prizes else 'N/A'
        }
    except requests.RequestException as e:
        print(f"Error scraping project {url}: {e}")
        return {}
    except AttributeError as e:
        print(f"Error parsing project details from {url}: {e}")
        return {}

def scrape_all_projects(urls: list, output_file: str, max_workers: int = 20) -> pd.DataFrame:
    """Scrape details from all project URLs concurrently and save to CSV"""
    all_project_details = []
    
    # Create a progress bar
    pbar = tqdm(total=len(urls), desc="Scraping projects")
    
    def scrape_with_progress(url):
        """Wrapper function to update progress bar after each scrape"""
        try:
            result = scrape_project_details(url, output_file)
            pbar.update(1)
            return result
        except Exception as e:
            print(f"\nError scraping {url}: {e}")
            pbar.update(1)
            return None
    
    # Use ThreadPoolExecutor for concurrent scraping
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all scraping tasks
        future_to_url = {executor.submit(scrape_with_progress, url): url for url in urls}
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                project_data = future.result()
                if project_data:  # Only add if we got data back
                    all_project_details.append(project_data)
            except Exception as e:
                print(f"\nError processing {url}: {e}")
    
    pbar.close()
    
    # Create DataFrame from all project details
    df = pd.DataFrame(all_project_details)
    
    # Create results directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Save to CSV with proper file handling
    try:
        # First, try to remove the file if it exists
        if os.path.exists(output_file):
            os.remove(output_file)
        
        # Write with context manager to ensure proper file closure
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            df.to_csv(f, 
                     index=False,
                     quoting=csv.QUOTE_ALL)
        
        print(f"\nSuccessfully saved to {output_file}")
    except Exception as e:
        print(f"Error saving CSV: {e}")
    
    print(f"\nTotal projects scraped: {len(all_project_details)}")
    return df

def get_hackathon_events(url: str = "https://ethglobal.com/events/hackathons") -> list:
    """
    Scrape all past hackathon event URLs from the events page
    
    Args:
        url: The events page URL
        
    Returns:
        list: List of event URLs
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the "Past" section and get all event links
        event_urls = []
        past_section = soup.find(text="Past")
        
        if past_section:
            # Get all links after the "Past" section
            for link in past_section.find_all_next('a', href=True):
                href = link['href']
                if href.startswith('/events/'):
                    full_url = f"https://ethglobal.com{href}"
                    event_urls.append(full_url)
        
        print(f"Found {len(event_urls)} past hackathon events")
        return event_urls
        
    except requests.RequestException as e:
        print(f"Error fetching events page: {e}")
        return []

def main():
    # Existing file names
    project_urls_csv = 'results/project_urls.csv'
    project_details_csv = 'results/ethglobal_project_details.csv'
    events_csv = 'results/ethglobal_events.csv'  # New file for events
    
    # Create results directory if it doesn't exist
    os.makedirs('results', exist_ok=True)
    
    # Clean up old files before starting
    for file in [project_urls_csv, project_details_csv, events_csv]:
        if os.path.exists(file):
            try:
                os.remove(file)
            except Exception as e:
                print(f"Warning: Could not remove old file {file}: {e}")
    
    # Step 0: Get hackathon events (new step)
    SCRAPE_EVENTS = True  # Toggle for event scraping
    if SCRAPE_EVENTS:
        event_urls = get_hackathon_events()
        events_df = pd.DataFrame(event_urls, columns=['event_url'])
        events_df.to_csv(events_csv, index=False)
        print(f"Saved {len(event_urls)} event URLs to {events_csv}")
    
    # Step 1: Scrape project URLs (only if needed)
    SCRAPE_URLS = False  # Toggle this when you need to scrape new URLs
    if SCRAPE_URLS:
        event_name = "bangkok"
        total_pages = 23
        project_urls = generate_urls(event=event_name, total_pages=total_pages)
        df_urls = scrape_event(project_urls, output_file=project_urls_csv)
    
    # Step 2: Scrape project details
    SCRAPE_DETAILS = True  # Toggle this when you want to scrape project details
    if SCRAPE_DETAILS:
        urls = read_project_urls(csv_path=project_urls_csv)  # Read URLs from the CSV
        df_details = scrape_all_projects(urls[0:30], output_file=project_details_csv)

if __name__ == "__main__":
    main()


