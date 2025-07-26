import time
import asyncio
from playwright.async_api import async_playwright
import smtplib
from email.message import EmailMessage
import os
import logging
from datetime import datetime
import json
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# ---- CONFIGURATION ----
THEATRE_URLS = [
"https://in.bookmyshow.com/cinemas/hyderabad/sudarshan-35mm-4k-laser-dolby-atmos-rtc-x-roads/buytickets/SUDA/20250809",
"https://in.bookmyshow.com/cinemas/hyderabad/prasads-multiplex-hyderabad/buytickets/PRHN/20250809",
"https://in.bookmyshow.com/cinemas/hyderabad/sudarshan-35mm-4k-laser-dolby-atmos-rtc-x-roads/buytickets/SUDA/20250808",
"https://in.bookmyshow.com/cinemas/hyderabad/prasads-multiplex-hyderabad/buytickets/PRHN/20250808",
]
MOVIE_NAME = "Athadu"

# Email configuration - use environment variables for security
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 465  # Use 587 for TLS or 465 for SSL
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'your_email@gmail.com')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', 'your_email_password')
# Support multiple recipients - comma-separated in environment variable
RECIPIENT_EMAILS = os.getenv('RECIPIENT_EMAILS', 'recipient@example.com').split(',')

# ---- SCRIPT LOGIC ----
def parse_venue_api_data(page_content, movie_name, target_date, url):
    """
    Parse venueShowtimesFunctionalApi data to check for movie availability
    Returns (movie_found, has_showtimes)
    """
    try:
        # Create a timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save the full page content for debugging
        page_filename = f"debug_page_content_{timestamp}.html"
        with open(page_filename, 'w', encoding='utf-8') as f:
            f.write(page_content)
        logging.info(f"Saved full page content to {page_filename}")
        
        # Look for the venueShowtimesFunctionalApi object
        if 'Event' not in page_content:
            logging.info("Event not found in page content")
            return False, False
        
        # Use regex to find the venueShowtimesFunctionalApi object
        # Look for the venueShowtimesFunctionalApi object with its queries
        api_pattern =r'"Event":(\[.*?\])\s*,\s*"Date"'
        api_match = re.search(api_pattern, page_content, re.DOTALL)
        
        # If the above pattern doesn't work, try a more general approach
        if not api_match:
            api_pattern = r'"Event":(\[.*?\])\s*,\s*"Date"'
            api_match = re.search(api_pattern, page_content, re.DOTALL)
        
        if not api_match:
            logging.info("Could not extract venueShowtimesFunctionalApi with regex")
            return False, False
        
        api_data_str = api_match.group(1)
        
        # Save the extracted API data for debugging
        api_filename = f"debug_api_data_{timestamp}.json"
        with open(api_filename, 'w', encoding='utf-8') as f:
            f.write(api_data_str)
        logging.info(f"Saved extracted API data to {api_filename}")
        
        # Parse the JSON data properly
        try:
            events_data = json.loads(api_data_str)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON data: {e}")
            return False, False
        
        movie_found = False
        has_showtimes = False
        
        # Iterate through events to find our movie
        for event in events_data:
            # Check EventTitle first (main movie title)
            event_title = event.get('EventTitle', '')
            if movie_name.lower() in event_title.lower():
                movie_found = True
                logging.info(f"Found movie '{movie_name}' in EventTitle: '{event_title}'")
                
                # Check if this event has ChildEvents with ShowTimes
                child_events = event.get('ChildEvents', [])
                for child_event in child_events:
                    show_times = child_event.get('ShowTimes', [])
                    
                    # Check if any show times are for our target date
                    for show_time in show_times:
                        show_date_code = show_time.get('ShowDateCode', '')
                        if show_date_code == target_date:
                            if 'prasads' in url:
                                if show_time.get('Attributes') == 'PCX SCREEN':
                                    has_showtimes = True
                                    show_time_str = show_time.get('ShowTime', '')
                                    logging.info(f"Found show time for {movie_name} on {target_date} at {show_time_str}")
                                    break
                                else:
                                    continue
                            else:
                                show_time_str = show_time.get('ShowTime', '')
                                logging.info(f"Found show time for {movie_name} on {target_date} at {show_time_str}")
                                has_showtimes = True
                                break
                    
                    if has_showtimes:
                        break
                
                if has_showtimes:
                    break
        
        # If not found in EventTitle, also check EventName in ChildEvents
        if not movie_found:
            for event in events_data:
                child_events = event.get('ChildEvents', [])
                for child_event in child_events:
                    event_name = child_event.get('EventName', '')
                    if movie_name.lower() in event_name.lower():
                        movie_found = True
                        logging.info(f"Found movie '{movie_name}' in EventName: '{event_name}'")
                        
                        # Check ShowTimes for this child event
                        show_times = child_event.get('ShowTimes', [])
                        for show_time in show_times:
                            show_date_code = show_time.get('ShowDateCode', '')
                            if show_date_code == target_date:
                                has_showtimes = True
                                show_time_str = show_time.get('ShowTime', '')
                                logging.info(f"Found show time for {movie_name} on {target_date} at {show_time_str}")
                                break
                        
                        if has_showtimes:
                            break
                
                if movie_found:
                    break
        
        # Save a summary of what we found
        summary_filename = f"debug_summary_{timestamp}.txt"
        with open(summary_filename, 'w', encoding='utf-8') as f:
            f.write(f"URL: {url}\n")
            f.write(f"Movie: {movie_name}\n")
            f.write(f"Target Date: {target_date}\n")
            f.write(f"Movie Found: {movie_found}\n")
            f.write(f"Has Showtimes: {has_showtimes}\n")
            f.write(f"Total Events: {len(events_data)}\n")
            if movie_found:
                f.write(f"Events checked: {[event.get('EventTitle', 'Unknown') for event in events_data]}\n")
        
        logging.info(f"Saved summary to {summary_filename}")
        
        return movie_found, has_showtimes
        
    except Exception as e:
        logging.error(f"Error parsing venue API data: {e}")
        return False, False

def extract_theatre_info(url):
    """Extract theatre name and date from URL"""
    try:
        # Parse URL to extract theatre name and date
        parts = url.split('/')
        theatre_part = parts[4]  # e.g., "prasads-multiplex-hyderabad"
        date_part = parts[-1]    # e.g., "20250809"
        
        # Convert theatre name to readable format
        theatre_name = theatre_part.replace('-', ' ').title()
        if 'prasads' in theatre_part.lower():
            theatre_name = "Prasads Multiplex"
        elif 'sudarshan' in theatre_part.lower():
            theatre_name = "Sudarshan 35mm"
        
        # Convert date to readable format
        year = date_part[:4]
        month = date_part[4:6]
        day = date_part[6:8]
        readable_date = f"{day}/{month}/{year}"
        
        return theatre_name, readable_date
    except Exception as e:
        logging.error(f"Error parsing URL {url}: {e}")
        return "Unknown Theatre", "Unknown Date"

async def check_movie():
    try:
        logging.info(f"Checking for {MOVIE_NAME} at {len(THEATRE_URLS)} theatres")
        available_theatres = []
        
        for url in THEATRE_URLS:
            try:
                logging.info(f"Checking {url}")
                
                async with async_playwright() as p:
                    # Launch browser with enhanced stealth settings
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-accelerated-2d-canvas',
                            '--no-first-run',
                            '--no-zygote',
                            '--disable-gpu',
                            '--disable-web-security',
                            '--disable-features=VizDisplayCompositor',
                            '--disable-background-timer-throttling',
                            '--disable-backgrounding-occluded-windows',
                            '--disable-renderer-backgrounding',
                            '--disable-field-trial-config',
                            '--disable-ipc-flooding-protection',
                            '--disable-hang-monitor',
                            '--disable-prompt-on-repost',
                            '--disable-client-side-phishing-detection',
                            '--disable-component-extensions-with-background-pages',
                            '--disable-default-apps',
                            '--disable-extensions',
                            '--disable-sync',
                            '--disable-translate',
                            '--hide-scrollbars',
                            '--mute-audio',
                            '--no-default-browser-check',
                            '--safebrowsing-disable-auto-update',
                            '--disable-blink-features=AutomationControlled'
                        ]
                    )
                    
                    context = await browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                        viewport={'width': 1920, 'height': 1080},
                        locale='en-US',
                        timezone_id='Asia/Kolkata',
                        extra_http_headers={
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'DNT': '1',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                            'Sec-Fetch-Dest': 'document',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-Site': 'none',
                            'Cache-Control': 'max-age=0'
                        }
                    )
                    
                    # Create a new page for each URL to avoid state issues
                    page = await context.new_page()
                    
                    # Navigate to the page with timeout
                    await page.goto(url, wait_until='networkidle', timeout=30000)
                    
                    # Wait a bit for any dynamic content to load
                    await page.wait_for_timeout(2000)
                    
                    # Check for movie availability using venueShowtimesFunctionalApi data
                    movie_found = False
                    has_showtimes = False
                    
                    try:
                        # Wait for the page to load and get the venueShowtimesFunctionalApi data
                        await page.wait_for_timeout(3000)  # Wait for API data to load
                        
                        # Extract the date from URL to verify it matches
                        url_date = url.split('/')[-1]  # e.g., "20250809"
                        
                        # Get the page content and look for venueShowtimesFunctionalApi data
                        page_content = await page.content()
                        
                        # Use the helper function to parse venue API data
                        movie_found, has_showtimes = parse_venue_api_data(page_content, MOVIE_NAME, url_date, url)
                        
                        if movie_found:
                            logging.info(f"Found {MOVIE_NAME} in venueShowtimesFunctionalApi data")
                            if has_showtimes:
                                logging.info(f"Found show times for {MOVIE_NAME} on date {url_date}")
                            else:
                                logging.info(f"Found {MOVIE_NAME} but no show times for date {url_date}")
                    
                    except Exception as e:
                        logging.debug(f"API data parsing failed: {e}")
                    
                    # Fallback: If API data parsing fails, try simple content search
                    if not movie_found:
                        try:
                            page_content = await page.content()
                            if MOVIE_NAME.lower() in page_content.lower():
                                # Additional check to ensure it's not just a false positive
                                if any(pattern in page_content.lower() for pattern in [
                                    f'"{MOVIE_NAME.lower()}"',
                                    f'/{MOVIE_NAME.lower()}/',
                                    'showtimes',
                                    'book tickets',
                                    'buy tickets'
                                ]):
                                    movie_found = True
                                    logging.info(f"Found {MOVIE_NAME} in page content (fallback)")
                        except Exception as e:
                            logging.debug(f"Fallback content search failed: {e}")
                    
                    # If movie found but no show times, it might be a false positive
                    if movie_found and not has_showtimes:
                        logging.info(f"Movie {MOVIE_NAME} found but no show times available for date {url_date}")
                        movie_found = False
                    
                    # Close the page and browser after checking
                    await page.close()
                    await browser.close()
                    
                    if movie_found:
                        theatre_name, date = extract_theatre_info(url)
                        available_theatres.append({
                            'url': url,
                            'theatre': theatre_name,
                            'date': date
                        })
                        logging.info(f"{MOVIE_NAME} is available at {theatre_name} on {date}!")
                    else:
                        logging.info(f"Movie not found at {url}")
                
                # Add 1-minute delay after processing each URL
                # logging.info(f"Waiting 1 minute before processing next URL...")
                # await asyncio.sleep(60)
            
            except Exception as e:
                logging.error(f"Error checking {url}: {e}")
                continue
        
        if available_theatres:
            logging.info(f"Found {MOVIE_NAME} at {len(available_theatres)} theatre(s)")
            return available_theatres
        else:
            logging.info(f"{MOVIE_NAME} not found at any of the theatres.")
            return []
    
    except Exception as e:
        logging.error(f"Unexpected error in check_movie: {e}")
        return []

def send_email(available_theatres):
    # Validate email configuration
    if SENDER_EMAIL == 'your_email@gmail.com' or not SENDER_EMAIL:
        logging.warning("Sender email not configured. Skipping email notification.")
        return
    
    if not SENDER_PASSWORD or SENDER_PASSWORD == 'your_email_password':
        logging.warning("Sender password not configured. Skipping email notification.")
        return
    
    if not available_theatres:
        logging.warning("No theatres available to send email about.")
        return
    
    if not RECIPIENT_EMAILS or RECIPIENT_EMAILS == ['recipient@example.com'] or not any(RECIPIENT_EMAILS):
        logging.warning("Recipient emails not configured. Skipping email notification.")
        return
    
    # Log email configuration (without sensitive data)
    logging.info(f"Attempting to send email from {SENDER_EMAIL} to {len(RECIPIENT_EMAILS)} recipient(s)")
    logging.info(f"Using SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        
    msg = EmailMessage()
    
    # Create subject line
    if len(available_theatres) == 1:
        theatre = available_theatres[0]
        msg['Subject'] = f"PENU TOOFANU thalonchi choosthe... tickets now available at {theatre['theatre']} on {theatre['date']}!"
    else:
        msg['Subject'] = f"PENU TOOFANU thalonchi choosthe... tickets now available at {len(available_theatres)} theatres!"
    
    msg['From'] = SENDER_EMAIL
    msg['To'] = ', '.join(RECIPIENT_EMAILS)  # Join multiple recipients with commas
    
    # Create email content
    content = f"Great news! '{MOVIE_NAME}' tickets are now available!\n\n"
    
    if len(available_theatres) == 1:
        theatre = available_theatres[0]
        content += f"Theatre: {theatre['theatre']}\n"
        content += f"Date: {theatre['date']}\n"
        content += f"Book here: {theatre['url']}\n"
    else:
        content += f"Available at {len(available_theatres)} theatres:\n\n"
        for i, theatre in enumerate(available_theatres, 1):
            content += f"{i}. {theatre['theatre']} - {theatre['date']}\n"
            content += f"   Book here: {theatre['url']}\n\n"
    
    content += f"\nMovie: {MOVIE_NAME}"
    msg.set_content(content)

    try:
        # Use SMTP_SSL for port 465 (SSL) or SMTP with starttls for port 587 (TLS)
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
                smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
                smtp.send_message(msg)
        logging.info(f"Notification email sent to {len(RECIPIENT_EMAILS)} recipient(s): {', '.join(RECIPIENT_EMAILS)}")
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        # Add more detailed error logging
        import traceback
        logging.error(f"Full error traceback: {traceback.format_exc()}")

async def main():
    logging.info("Movie notification check started!")
    logging.info(f"Checking for '{MOVIE_NAME}'")
    
    # Check once and send notification if found
    available_theatres = await check_movie()
    if available_theatres:
        send_email(available_theatres)
        logging.info("Movie found! Notification sent.")
    else:
        logging.info("Movie not found. No notification sent.")
    
    logging.info("Check completed. Exiting...")

if __name__ == "__main__":
    asyncio.run(main())
