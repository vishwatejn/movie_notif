import time
import requests
from bs4 import BeautifulSoup
import smtplib
from email.message import EmailMessage
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# ---- CONFIGURATION ----
THEATRE_URLS = ["https://in.bookmyshow.com/cinemas/hyderabad/prasads-multiplex-hyderabad/buytickets/PRHN/20250809",
"https://in.bookmyshow.com/cinemas/hyderabad/sudarshan-35mm-4k-laser-dolby-atmos-rtc-x-roads/buytickets/SUDA/20250809",
"https://in.bookmyshow.com/cinemas/hyderabad/prasads-multiplex-hyderabad/buytickets/PRHN/20250810",
"https://in.bookmyshow.com/cinemas/hyderabad/sudarshan-35mm-4k-laser-dolby-atmos-rtc-x-roads/buytickets/SUDA/20250810",
"https://in.bookmyshow.com/cinemas/hyderabad/prasads-multiplex-hyderabad/buytickets/PRHN/20250724"]
MOVIE_NAME = "Hari Hara Veera Mallu - Part 1 Sword vs Spirit"

# Headers to mimic a real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# Email configuration - use environment variables for security
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 465
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'your_email@gmail.com')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD', 'your_email_password')
# Support multiple recipients - comma-separated in environment variable
RECIPIENT_EMAILS = os.getenv('RECIPIENT_EMAILS', 'recipient@example.com').split(',')

# ---- SCRIPT LOGIC ----
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

def check_movie():
    try:
        logging.info(f"Checking for {MOVIE_NAME} at {len(THEATRE_URLS)} theatres")
        available_theatres = []
        
        for url in THEATRE_URLS:
            try:
                response = requests.get(url, headers=HEADERS, timeout=30)
                if response.status_code != 200:
                    logging.error(f"Failed to fetch page {url}: {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                if MOVIE_NAME.lower() in soup.text.lower():
                    theatre_name, date = extract_theatre_info(url)
                    available_theatres.append({
                        'url': url,
                        'theatre': theatre_name,
                        'date': date
                    })
                    logging.info(f"{MOVIE_NAME} is available at {theatre_name} on {date}!")
                
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error for {url}: {e}")
                continue
            except Exception as e:
                logging.error(f"Unexpected error for {url}: {e}")
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
    if SENDER_EMAIL == 'your_email@gmail.com':
        logging.warning("Email not configured. Skipping email notification.")
        return
    
    if not available_theatres:
        logging.warning("No theatres available to send email about.")
        return
    
    if not RECIPIENT_EMAILS or RECIPIENT_EMAILS == ['recipient@example.com']:
        logging.warning("Recipient emails not configured. Skipping email notification.")
        return
        
    msg = EmailMessage()
    
    # Create subject line
    if len(available_theatres) == 1:
        theatre = available_theatres[0]
        msg['Subject'] = f"'{MOVIE_NAME}' tickets now available at {theatre['theatre']} on {theatre['date']}!"
    else:
        msg['Subject'] = f"'{MOVIE_NAME}' tickets now available at {len(available_theatres)} theatres!"
    
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
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.send_message(msg)
        logging.info(f"Notification email sent to {len(RECIPIENT_EMAILS)} recipient(s): {', '.join(RECIPIENT_EMAILS)}")
    except Exception as e:
        logging.error(f"Error sending email: {e}")

def main():
    logging.info("Movie notification check started!")
    logging.info(f"Checking for '{MOVIE_NAME}'")
    
    # Check once and send notification if found
    available_theatres = check_movie()
    if available_theatres:
        send_email(available_theatres)
        logging.info("Movie found! Notification sent.")
    else:
        logging.info("Movie not found. No notification sent.")
    
    logging.info("Check completed. Exiting...")

if __name__ == "__main__":
    main()
