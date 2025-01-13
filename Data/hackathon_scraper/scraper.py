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
    Get all event URLs from the page without filtering
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get all links from the page
        all_links = []
        for link in soup.find_all('a', href=True):
            print(link)
            href = link['href']
            if href.startswith('/events/'):  # Only get event links
                full_url = f"https://ethglobal.com{href}"
                if full_url not in all_links:  # Avoid duplicates
                    all_links.append(full_url)
        
        print(f"Found {len(all_links)} total links")
        for link in all_links:
            print(f"Found: {link}")
            
        return all_links
        
    except requests.RequestException as e:
        print(f"Error fetching page: {e}")
        return []

def extract_event_details(url: str) -> dict:
    """Extract hackathon name, location, and year from event URL"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get event title from the URL first (more reliable)
        event_path = url.split('/')[-1]  # Get the last part of the URL
        
        # Clean up the event name
        event_name = event_path.replace('-', ' ').title()
        if 'ETH' not in event_name and 'Eth' not in event_name:
            event_name = f"ETHGlobal {event_name}"
        
        # Extract location from event name
        location = event_name
        if 'ETHGlobal' in location:
            location = location.replace('ETHGlobal', '').strip()
        if 'ETH' in location:
            location = location.replace('ETH', '').strip()
        
        # Find date information
        date_text = ''
        for text in soup.stripped_strings:
            if any(month in text for month in ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']):
                date_text = text
                break
        
        # Extract year from date
        year = 'N/A'
        if date_text:
            for word in date_text.split():
                if word.isdigit() and len(word) == 4:
                    year = word
                    break
        
        # Clean up special cases
        if location.lower() in ['online', 'virtual']:
            event_name = f"ETH{event_name}"
            location = 'Virtual'
        
        return {
            'event_name': event_name,
            'location': location,
            'year': year
        }
    except Exception as e:
        print(f"Error extracting event details from {url}: {e}")
        return {'event_name': 'N/A', 'location': 'N/A', 'year': 'N/A'}

def scrape_partners_and_prizes(event_url: str) -> tuple:
    """Scrape partners and prize information for an event"""
    try:
        # Get the prizes page URL
        prizes_url = f"{event_url}/prizes"
        print(f"Fetching prizes from: {prizes_url}")
        response = requests.get(prizes_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        prizes = []
        
        # Find all divs with border-b-2 class that contain prize information
        prize_divs = soup.find_all('div', class_='border-b-2')
        print(f"Found {len(prize_divs)} partner sections")
        
        for prize_div in prize_divs:
            try:
                # Get partner name and total amount
                h2_tag = prize_div.find('h2')
                if not h2_tag:
                    continue
                    
                partner_name = h2_tag.get_text(strip=True)
                total_amount = prize_div.find('p', class_='text-2xl').get_text(strip=True)
                
                # Find all prize sections
                prize_sections = prize_div.find_all('div', {'data-state': 'open', 'id': 'collapsible-data'})
                
                for section in prize_sections:
                    # Find the prize header containing title
                    prize_header = section.find('span', class_='text-xl font-semibold break-normal')
                    if not prize_header:
                        continue
                        
                    amount_span = section.find('span', class_='text-xl font-medium')
                    if not amount_span:
                        continue
                    
                    # Clean title by removing emoji
                    title = prize_header.get_text(strip=True)
                    title = ''.join(c for c in title if not (0x1F300 <= ord(c) <= 0x1F9FF))  # Remove emoji
                    title = title.strip()
                    amount = amount_span.get_text(strip=True)
                    
                    # Get description - look for the text div that comes after the prize breakdown
                    breakdown_div = section.find('div', class_='group flex text-md')
                    if breakdown_div:
                        desc_div = breakdown_div.find_next_sibling('div', class_='text-lg mt-1.5 mb-2')
                        description = desc_div.get_text(strip=True) if desc_div else 'N/A'
                    else:
                        description = 'N/A'
                    
                    # Get prize breakdown
                    breakdowns = []
                    breakdown_div = section.find('div', class_='flex flex-col lg:flex-row gap-y-2 gap-x-10')
                    if breakdown_div:
                        for place in breakdown_div.find_all('div', class_='flex gap-x-1'):
                            place_info = place.find('div', class_='flex flex-col')
                            if place_info:
                                place_name = place_info.find('div', class_='w-fit').get_text(strip=True)
                                amount_div = place_info.find('div', class_='text-gray-900')
                                place_amount = amount_div.get_text(strip=True) if amount_div else 'N/A'
                                breakdowns.append(f"{place_name}: {place_amount}")
                    
                    prizes.append({
                        'event_url': event_url,
                        'partner_name': partner_name,
                        'total_partner_amount': total_amount,
                        'prize_title': title,
                        'prize_amount': amount,
                        'description': description,
                        'prize_breakdown': ' | '.join(breakdowns) if breakdowns else 'N/A'
                    })
                    
            except Exception as e:
                print(f"Error processing partner section: {e}")
                continue
        
        print(f"Found {len(prizes)} prizes")
        return [], prizes
        
    except Exception as e:
        print(f"Error scraping prizes from {event_url}: {e}")
        return [], []

def scrape_all_events_data(events_csv: str, partners_output: str, prizes_output: str) -> tuple:
    """Scrape partners and prizes for all events"""
    # Read events from CSV
    events_df = pd.read_csv(events_csv)
    all_partners = []
    all_prizes = []
    
    # Create progress bar
    with tqdm(total=len(events_df), desc="Scraping events") as pbar:
        for event_url in events_df['event_url']:
            print(f"\nProcessing event: {event_url}")
            partners, prizes = scrape_partners_and_prizes(event_url)
            if partners:
                all_partners.extend(partners)
                print(f"Added {len(partners)} partners")
            if prizes:
                all_prizes.extend(prizes)
                print(f"Added {len(prizes)} prizes")
            pbar.update(1)
    
    print(f"\nTotal partners found: {len(all_partners)}")
    print(f"Total prizes found: {len(all_prizes)}")
    
    # Convert to DataFrames and save
    if all_partners:
        partners_df = pd.DataFrame(all_partners)
        partners_df.to_csv(partners_output, index=False, quoting=csv.QUOTE_ALL)
        print(f"Saved partners to {partners_output}")
    else:
        print("Warning: No partners found!")
        partners_df = pd.DataFrame()
    
    if all_prizes:
        prizes_df = pd.DataFrame(all_prizes)
        prizes_df.to_csv(prizes_output, index=False, quoting=csv.QUOTE_ALL)
        print(f"Saved prizes to {prizes_output}")
    else:
        print("Warning: No prizes found!")
        prizes_df = pd.DataFrame()
    
    return partners_df, prizes_df

def main():
    # Test prize scraping directly with a specific URL
    test_url = "https://ethglobal.com/events/sanfrancisco2024"
    prizes_output = 'results/ethglobal_prizes.csv'
    
    print(f"\nScraping prizes from: {test_url}")
    _, prizes = scrape_partners_and_prizes(test_url)
    
    if prizes:
        prizes_df = pd.DataFrame(prizes)
        prizes_df.to_csv(prizes_output, index=False, quoting=csv.QUOTE_ALL)
        print(f"Saved {len(prizes)} prizes to {prizes_output}")
        
        # Print first prize for debugging
        if len(prizes) > 0:
            print("\nExample prize data:")
            for key, value in prizes[0].items():
                print(f"{key}: {value}")
    else:
        print("No prizes found!")

if __name__ == "__main__":
    main()


