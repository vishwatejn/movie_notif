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
# Theatre URL to email mapping - each theatre can have specific recipients
# Format: "theatre_url": "comma_separated_emails"
THEATRE_EMAIL_MAPPING = {
    "https://in.bookmyshow.com/cinemas/hyderabad/amb-cinemas-gachibowli/buytickets/AMBH/20250730": os.getenv('AMB_0730_EMAILS', ''),
    "https://in.bookmyshow.com/cinemas/hyderabad/amb-cinemas-gachibowli/buytickets/AMBH/20250731": os.getenv('AMB_0731_EMAILS', ''),
}

# Get all unique theatre URLs for checking
THEATRE_URLS = list(THEATRE_EMAIL_MAPPING.keys())

MOVIE_NAME = "Kingdom"

# Email configuration - use environment variables for security
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 465  # Use 587 for TLS or 465 for SSL
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'your_email@gmail.com')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', 'your_email_password')

# Notification tracking file
NOTIFICATION_TRACKING_FILE = 'notification_tracking.json'

# ---- NOTIFICATION TRACKING FUNCTIONS ----
def load_notification_tracking():
    """Load notification tracking data from file"""
    try:
        if os.path.exists(NOTIFICATION_TRACKING_FILE):
            # Check if file is empty
            if os.path.getsize(NOTIFICATION_TRACKING_FILE) == 0:
                logging.info("Notification tracking file is empty, starting fresh")
                return {}
            
            with open(NOTIFICATION_TRACKING_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    logging.info("Notification tracking file is empty, starting fresh")
                    return {}
                
                tracking_data = json.loads(content)
                logging.info(f"Loaded notification tracking data: {len(tracking_data)} entries")
                return tracking_data
        else:
            logging.info("No notification tracking file found, starting fresh")
            return {}
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in notification tracking file: {e}")
        logging.info("Creating backup of corrupted file and starting fresh")
        # Create backup of corrupted file
        backup_name = f"{NOTIFICATION_TRACKING_FILE}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            os.rename(NOTIFICATION_TRACKING_FILE, backup_name)
            logging.info(f"Corrupted file backed up as {backup_name}")
        except Exception as backup_error:
            logging.error(f"Failed to backup corrupted file: {backup_error}")
        return {}
    except Exception as e:
        logging.error(f"Error loading notification tracking: {e}")
        return {}

def save_notification_tracking(tracking_data):
    """Save notification tracking data to file and commit to git for persistence"""
    try:
        # Save to file
        with open(NOTIFICATION_TRACKING_FILE, 'w', encoding='utf-8') as f:
            json.dump(tracking_data, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved notification tracking data: {len(tracking_data)} entries")
        
        # Commit to git for persistence between runs
        try:
            import subprocess
            import os
            
            # Check if we're in a git repository
            result = subprocess.run(['git', 'status'], capture_output=True, text=True, cwd='.')
            if result.returncode == 0:
                # We're in a git repo, commit the tracking file
                subprocess.run(['git', 'add', NOTIFICATION_TRACKING_FILE], check=True, cwd='.')
                subprocess.run(['git', 'config', '--local', 'user.email', 'movie-notifier@github.actions'], check=True, cwd='.')
                subprocess.run(['git', 'config', '--local', 'user.name', 'Movie Notifier Bot'], check=True, cwd='.')
                
                # Check if there are changes to commit
                status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, cwd='.')
                if status_result.stdout.strip():
                    commit_message = f"Update notification tracking - {len(tracking_data)} entries - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    subprocess.run(['git', 'commit', '-m', commit_message], check=True, cwd='.')
                    logging.info(f"Committed tracking data to git: {commit_message}")
                    
                    # Push changes to remote repository
                    try:
                        subprocess.run(['git', 'push', 'origin', 'main'], check=True, cwd='.')
                        logging.info("Pushed tracking data to remote repository")
                    except subprocess.CalledProcessError as push_error:
                        logging.warning(f"Failed to push tracking data to remote: {push_error}")
                        logging.info("Tracking data committed locally but not pushed to remote")
                else:
                    logging.info("No changes to commit in tracking file")
            else:
                logging.info("Not in a git repository, skipping git commit")
                
        except subprocess.CalledProcessError as e:
            logging.warning(f"Failed to commit tracking data to git: {e}")
            logging.info("Tracking data saved to file but not committed to git")
        except Exception as e:
            logging.warning(f"Error with git operations: {e}")
            logging.info("Tracking data saved to file but git operations failed")
            
    except Exception as e:
        logging.error(f"Error saving notification tracking: {e}")

def create_notification_key(theatre_url, recipient_emails):
    """Create a unique key for tracking notifications"""
    # Extract theatre name and date from URL
    theatre_name, date = extract_theatre_info(theatre_url)
    # Create a unique key combining theatre, date, and recipients
    #recipient_key = ','.join(sorted(recipient_emails))
    return f"{theatre_name}_{date}_{MOVIE_NAME}"

def is_notification_sent(theatre_url, recipient_emails, tracking_data):
    """Check if notification was already sent for this theatre/date/recipients combination"""
    notification_key = create_notification_key(theatre_url, recipient_emails)
    return notification_key in tracking_data

def mark_notification_sent(theatre_url, recipient_emails, tracking_data):
    """Mark notification as sent for this theatre/date/recipients combination"""
    notification_key = create_notification_key(theatre_url, recipient_emails)
    tracking_data[notification_key] = {
        'theatre_url': theatre_url,
        'sent_at': datetime.now().isoformat(),
        'movie_name': MOVIE_NAME
    }
    return tracking_data

def filter_new_notifications(available_theatres, tracking_data):
    """Filter out theatres that have already been notified"""
    new_notifications = []
    
    for theatre in available_theatres:
        url = theatre['url']
        if url in THEATRE_EMAIL_MAPPING:
            recipient_emails = THEATRE_EMAIL_MAPPING[url]
            if recipient_emails:
                emails = [email.strip() for email in recipient_emails.split(',') if email.strip()]
                if emails:
                    if not is_notification_sent(url, emails, tracking_data):
                        new_notifications.append(theatre)
                        logging.info(f"New notification needed for {theatre['theatre']} on {theatre['date']}")
                    else:
                        logging.info(f"Notification already sent for {theatre['theatre']} on {theatre['date']}")
                else:
                    logging.warning(f"No valid emails configured for theatre {url}")
            else:
                logging.warning(f"No emails configured for theatre {url}")
        else:
            logging.warning(f"No email mapping found for theatre {url}")
    
    return new_notifications

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
    # Load existing notification tracking
    tracking_data = load_notification_tracking()
    
    # Filter out already notified theatres
    new_notifications = filter_new_notifications(available_theatres, tracking_data)
    
    if not new_notifications:
        logging.info("No new notifications to send - all theatres already notified")
        return
    
    # Validate email configuration
    if SENDER_EMAIL == 'your_email@gmail.com' or not SENDER_EMAIL:
        logging.warning("Sender email not configured. Skipping email notification.")
        return
    
    if not SENDER_PASSWORD or SENDER_PASSWORD == 'your_email_password':
        logging.warning("Sender password not configured. Skipping email notification.")
        return
    
    # Log email configuration (without sensitive data)
    logging.info(f"Attempting to send emails from {SENDER_EMAIL}")
    logging.info(f"Using SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
    
    # Group theatres by their email recipients
    email_groups = {}
    for theatre in new_notifications:
        url = theatre['url']
        if url in THEATRE_EMAIL_MAPPING:
            recipient_emails = THEATRE_EMAIL_MAPPING[url]
            if recipient_emails:
                # Split comma-separated emails and clean them
                emails = [email.strip() for email in recipient_emails.split(',') if email.strip()]
                if emails:
                    # Use tuple of emails as key for grouping
                    email_key = tuple(sorted(emails))
                    if email_key not in email_groups:
                        email_groups[email_key] = []
                    email_groups[email_key].append(theatre)
                else:
                    logging.warning(f"No valid emails configured for theatre {url}")
            else:
                logging.warning(f"No emails configured for theatre {url}")
        else:
            logging.warning(f"No email mapping found for theatre {url}")
    
    if not email_groups:
        logging.warning("No valid email recipients found for any available theatres.")
        return
    
    # Send separate emails to each group of recipients
    for recipient_emails, theatres in email_groups.items():
        try:
            msg = EmailMessage()
            
            # Create subject line
            if len(theatres) == 1:
                theatre = theatres[0]
                msg['Subject'] = f"PENU TOOFANU thalonchi choosthe... tickets now available at {theatre['theatre']} on {theatre['date']}!"
            else:
                msg['Subject'] = f"PENU TOOFANU thalonchi choosthe... tickets now available at {len(theatres)} theatres!"
            
            msg['From'] = SENDER_EMAIL
            msg['Bcc'] = ', '.join(recipient_emails)
            
            # Create email content
            content = f"Great news! '{MOVIE_NAME}' tickets are now available!\n\n"
            
            if len(theatres) == 1:
                theatre = theatres[0]
                content += f"Theatre: {theatre['theatre']}\n"
                content += f"Date: {theatre['date']}\n"
                content += f"Book here: {theatre['url']}\n"
            else:
                content += f"Available at {len(theatres)} theatres:\n\n"
                for i, theatre in enumerate(theatres, 1):
                    content += f"{i}. {theatre['theatre']} - {theatre['date']}\n"
                    content += f"   Book here: {theatre['url']}\n\n"
            
            content += f"\nMovie: {MOVIE_NAME}"
            msg.set_content(content)

            # Send the email
            if SMTP_PORT == 465:
                with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
                    smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
                    smtp.starttls()
                    smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
                    smtp.send_message(msg)
            
            # Mark notifications as sent for all theatres in this email
            for theatre in theatres:
                url = theatre['url']
                if url in THEATRE_EMAIL_MAPPING:
                    recipient_emails_str = THEATRE_EMAIL_MAPPING[url]
                    if recipient_emails_str:
                        emails = [email.strip() for email in recipient_emails_str.split(',') if email.strip()]
                        if emails:
                            tracking_data = mark_notification_sent(url, emails, tracking_data)
            
            logging.info(f"Notification email sent to {len(recipient_emails)} recipient(s): {', '.join(recipient_emails)}")
            logging.info(f"Email covered {len(theatres)} theatre(s): {[t['theatre'] for t in theatres]}")
            
        except Exception as e:
            logging.error(f"Error sending email to {', '.join(recipient_emails)}: {e}")
            # Add more detailed error logging
            import traceback
            logging.error(f"Full error traceback: {traceback.format_exc()}")
    
    # Save updated tracking data
    save_notification_tracking(tracking_data)

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
