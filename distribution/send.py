#!/usr/bin/env python3
"""
Newsletter Distribution Script

Sends the latest newsletter from the output folder to all subscribers
using the Resend API.

Usage:
    python distribution/send.py
    python distribution/send.py --newsletter output/newsletter-2026-01.html
    python distribution/send.py --dry-run

Environment Variables:
    RESEND_API_KEY: Your Resend API key (required)

Email Authentication Requirements:
    For deliverability (especially to Apple Mail/iCloud), ensure your domain has:
    - SPF record configured
    - DKIM signing enabled (Resend handles this automatically)
    - DMARC policy published (recommended: p=quarantine or p=reject)
    
    Check Resend documentation for DNS setup:
    https://resend.com/docs/dashboard/domains/introduction
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path, override=True)
except ImportError:
    pass  # dotenv not installed, rely on system environment variables

try:
    import resend
except ImportError:
    print("Error: resend package not installed. Run: pip install resend")
    sys.exit(1)

# Configuration
SENDER_ADDRESS = "Philipp Dubach <newsletter@m.philippdubach.com>"
REPLY_TO = "me@philippdubach.com"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
SUBSCRIBERS_FILE = Path(__file__).parent / "subscribers.csv"
TOKENS_FILE = Path(__file__).parent / "unsubscribe_tokens.json"

# Rate limiting: Resend allows 2 requests/second, we'll be conservative
RATE_LIMIT_DELAY = 0.6  # seconds between emails
BATCH_SIZE = 50  # Max recipients per batch (Resend limit)

# DNS records to verify for email authentication
DNS_CHECKS = {
    "SPF": ("m.philippdubach.com", "TXT", "v=spf1 include:amazonses.com"),
    "DKIM": ("resend._domainkey.m.philippdubach.com", "TXT", "p=MIGfMA0GCSqGSIb3DQEBAQUAA"),
    "DMARC": ("_dmarc.m.philippdubach.com", "TXT", "v=DMARC1"),
}


def get_latest_newsletter() -> Optional[Path]:
    """Find the most recent newsletter HTML file in the output directory."""
    if not OUTPUT_DIR.exists():
        return None
    
    html_files = list(OUTPUT_DIR.glob("newsletter-*.html"))
    if not html_files:
        return None
    
    # Sort by filename (date format ensures correct ordering)
    html_files.sort(key=lambda f: f.name, reverse=True)
    return html_files[0]


def extract_subject_from_html(html_path: Path) -> str:
    """Extract the title from the HTML file for use as email subject."""
    content = html_path.read_text(encoding="utf-8")
    
    # Try to find <title> tag
    title_match = re.search(r"<title>([^<]+)</title>", content, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()
    
    # Fallback to filename-based subject
    name = html_path.stem  # e.g., "newsletter-2026-01"
    match = re.match(r"newsletter-(\d{4})-(\d{2})", name)
    if match:
        year, month = match.groups()
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = months[int(month) - 1]
        return f"philippdubach.com - {month_name} {year} Newsletter"
    
    return f"philippdubach.com Newsletter"


def load_subscribers(csv_path: Path) -> List[Dict]:
    """Load subscribers from CSV file. Expected columns: email, name (optional)."""
    if not csv_path.exists():
        print(f"Error: Subscribers file not found: {csv_path}")
        print("Create a CSV file with 'email' column (and optional 'name' column)")
        sys.exit(1)
    
    subscribers = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        if "email" not in reader.fieldnames:
            print("Error: CSV must have an 'email' column")
            sys.exit(1)
        
        for row in reader:
            email = row["email"].strip()
            if email and "@" in email:
                name = row.get("name", "").strip()
                subscribers.append({"email": email, "name": name})
    
    return subscribers


def format_recipient(subscriber: dict) -> str:
    """Format subscriber as email address with optional name."""
    if subscriber["name"]:
        return f"{subscriber['name']} <{subscriber['email']}>"
    return subscriber["email"]


def send_newsletter(
    html_path: Path,
    subscribers: List[Dict],
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Send newsletter to all subscribers.
    
    Returns tuple of (successful_count, failed_count).
    """
    html_content = html_path.read_text(encoding="utf-8")
    subject = extract_subject_from_html(html_path)
    
    # Load or create token store
    if TOKENS_FILE.exists():
        with open(TOKENS_FILE, 'r') as f:
            token_store = json.load(f)
    else:
        token_store = {}
    
    print(f"\nSubject: {subject}")
    print(f"From: {SENDER_ADDRESS}")
    print(f"Reply-To: {REPLY_TO}")
    print(f"Recipients: {len(subscribers)}")
    
    if dry_run:
        print("\n[DRY RUN] Would send to:")
        for sub in subscribers:
            print(f"  - {format_recipient(sub)}")
        return len(subscribers), 0
    
    # Initialize Resend
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("\nError: RESEND_API_KEY environment variable not set")
        print("Get your API key from: https://resend.com/api-keys")
        sys.exit(1)
    
    resend.api_key = api_key
    
    success_count = 0
    fail_count = 0
    
    print("\nSending emails...")
    
    for i, subscriber in enumerate(subscribers, 1):
        recipient = format_recipient(subscriber)
        
        # Generate unique unsubscribe token
        token_data = f"{subscriber['email']}:{html_path.stem}"
        token = hashlib.sha256(token_data.encode()).hexdigest()[:32]
        
        # Store token mapping
        token_store[token] = {
            "email": subscriber["email"],
            "newsletter": html_path.stem,
            "sent_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            params: resend.Emails.SendParams = {
                "from": SENDER_ADDRESS,
                "to": [subscriber["email"]],
                "subject": subject,
                "html": html_content,
                "reply_to": REPLY_TO,
                "headers": {
                    # RFC 2369 + RFC 8058 - List-Unsubscribe with both HTTPS and mailto
                    "List-Unsubscribe": f"<https://philippdubach.com/api/unsubscribe?token={token}>, <mailto:{REPLY_TO}?subject=Unsubscribe>",
                    # RFC 8058 - One-click unsubscribe (must be exact format)
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    # List identification (RFC 2919)
                    "List-Id": f"<newsletter.philippdubach.com>",
                    # Indicate this is bulk/marketing email
                    "Precedence": "bulk",
                    # Help prevent threading
                    "X-Entity-Ref-ID": html_path.stem,
                    # Auto-Submitted header to indicate automated email
                    "Auto-Submitted": "auto-generated",
                    # Feedback ID for tracking (helps with reputation)
                    "Feedback-ID": f"newsletter:{html_path.stem}:philippdubach.com",
                },
                "tags": [
                    {"name": "newsletter", "value": html_path.stem},
                    {"name": "type", "value": "newsletter"},
                ]
            }
            
            result = resend.Emails.send(params)
            success_count += 1
            print(f"  [{i}/{len(subscribers)}] Sent to {subscriber['email']} (id: {result['id']})")
            
        except Exception as e:
            fail_count += 1
            print(f"  [{i}/{len(subscribers)}] Failed: {subscriber['email']} - {e}")
        
        # Rate limiting
        if i < len(subscribers):
            time.sleep(RATE_LIMIT_DELAY)
    
    # Save token store
    with open(TOKENS_FILE, 'w') as f:
        json.dump(token_store, f, indent=2)
    
    print(f"\n💾 Saved {len(token_store)} unsubscribe tokens to {TOKENS_FILE.name}")
    
    return success_count, fail_count


def confirm_send(html_path: Path, subscriber_count: int) -> bool:
    """Ask user to confirm before sending."""
    print("\n" + "=" * 60)
    print("NEWSLETTER DISTRIBUTION")
    print("=" * 60)
    print(f"\nNewsletter: {html_path.name}")
    print(f"Recipients: {subscriber_count}")
    print(f"Sender: {SENDER_ADDRESS}")
    print(f"Reply-To: {REPLY_TO}")
    
    response = input("\nIs this the correct newsletter? Open in browser to verify? [Y/n]: ").strip().lower()
    
    if response not in ("", "y", "yes"):
        return False
    
    # Open in browser for verification
    print(f"\nOpening {html_path.name} in browser...")
    webbrowser.open(f"file://{html_path.absolute()}")
    
    response = input("\nProceed with sending? [y/N]: ").strip().lower()
    return response in ("y", "yes")


def verify_dns_records() -> Dict[str, bool]:
    """
    Verify SPF, DKIM, and DMARC records are properly configured.
    Returns dict with check results.
    """
    results = {}
    
    print("\n" + "=" * 60)
    print("EMAIL AUTHENTICATION CHECK")
    print("=" * 60)
    
    try:
        import dns.resolver
        dns_available = True
    except ImportError:
        print("\n⚠️  Warning: dnspython not installed")
        print("   Run: pip install dnspython")
        print("   Skipping DNS verification...\n")
        return {"dns_available": False}
    
    for check_name, (domain, record_type, expected_content) in DNS_CHECKS.items():
        try:
            answers = dns.resolver.resolve(domain, record_type, lifetime=5)
            found = False
            
            for rdata in answers:
                record_value = rdata.to_text().strip('"')
                if expected_content in record_value:
                    found = True
                    break
            
            if found:
                print(f"✅ {check_name:6} - {domain}")
                results[check_name] = True
            else:
                print(f"❌ {check_name:6} - Record exists but doesn't match expected value")
                print(f"           Domain: {domain}")
                results[check_name] = False
                
        except dns.resolver.NXDOMAIN:
            print(f"❌ {check_name:6} - Record not found: {domain}")
            results[check_name] = False
        except dns.resolver.NoAnswer:
            print(f"❌ {check_name:6} - No {record_type} record: {domain}")
            results[check_name] = False
        except dns.resolver.Timeout:
            print(f"⚠️  {check_name:6} - DNS query timeout: {domain}")
            results[check_name] = None
        except Exception as e:
            print(f"⚠️  {check_name:6} - Error checking: {e}")
            results[check_name] = None
    
    print()
    
    # Summary
    all_passed = all(v is True for v in results.values() if v is not None)
    if all_passed:
        print("✅ All email authentication checks passed!")
    else:
        failed = [k for k, v in results.items() if v is False]
        if failed:
            print(f"⚠️  Warning: Failed checks: {', '.join(failed)}")
            print("   This may cause deliverability issues, especially with Apple Mail.")
    
    results["all_passed"] = all_passed
    return results


def wait_with_wakelock(delay_seconds: int) -> None:
    """
    Wait for the specified delay while keeping the system awake.
    Uses macOS caffeinate command to prevent sleep during wait.
    """
    if delay_seconds <= 0:
        return
    
    hours = delay_seconds // 3600
    minutes = (delay_seconds % 3600) // 60
    seconds = delay_seconds % 60
    
    time_parts = []
    if hours > 0:
        time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    
    time_str = ", ".join(time_parts) if time_parts else "0 seconds"
    
    print(f"\n⏰ Waiting {time_str} before sending...")
    print(f"   System will stay awake during this time")
    
    send_time = time.time() + delay_seconds
    send_datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(send_time))
    print(f"   Scheduled send time: {send_datetime}")
    print(f"   Press Ctrl+C to cancel\n")
    
    try:
        # Use caffeinate to prevent system sleep on macOS
        # -d: Prevent the display from sleeping
        # -i: Prevent the system from idle sleeping
        # -s: Prevent the system from sleeping when on AC power
        subprocess.run(
            ["caffeinate", "-dis", "sleep", str(delay_seconds)],
            check=True
        )
        print("\n✓ Wait complete. Proceeding with send...")
    except KeyboardInterrupt:
        print("\n\n⚠️  Wait cancelled by user. Aborting send.")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"\n⚠️  Warning: caffeinate failed ({e}). Using regular sleep...")
        try:
            time.sleep(delay_seconds)
        except KeyboardInterrupt:
            print("\n\n⚠️  Wait cancelled by user. Aborting send.")
            sys.exit(0)
    except FileNotFoundError:
        # caffeinate not available (not on macOS)
        print(f"   Note: caffeinate not available, using regular sleep")
        try:
            time.sleep(delay_seconds)
        except KeyboardInterrupt:
            print("\n\n⚠️  Wait cancelled by user. Aborting send.")
            sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Send newsletter to subscribers via Resend API"
    )
    parser.add_argument(
        "--newsletter",
        type=Path,
        help="Path to specific newsletter HTML file (default: latest)"
    )
    parser.add_argument(
        "--subscribers",
        type=Path,
        default=SUBSCRIBERS_FILE,
        help="Path to subscribers CSV file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without actually sending"
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompts (use with caution)"
    )
    
    args = parser.parse_args()
    
    # Find newsletter to send
    if args.newsletter:
        html_path = args.newsletter
        if not html_path.exists():
            print(f"Error: Newsletter file not found: {html_path}")
            sys.exit(1)
    else:
        html_path = get_latest_newsletter()
        if not html_path:
            print("Error: No newsletter files found in output directory")
            sys.exit(1)
    
    # Load subscribers
    subscribers = load_subscribers(args.subscribers)
    if not subscribers:
        print("Error: No valid subscribers found in CSV")
        sys.exit(1)
    
    # Verify DNS records before sending
    if not args.no_confirm and not args.dry_run:
        dns_results = verify_dns_records()
        
        if not dns_results.get("all_passed", False) and dns_results.get("dns_available", True):
            response = input("\nDNS checks failed. Continue anyway? [y/N]: ").strip().lower()
            if response not in ("y", "yes"):
                print("\nAborted. Fix DNS records and try again.")
                sys.exit(0)
    
    # Confirm before sending
    if not args.no_confirm and not args.dry_run:
        if not confirm_send(html_path, len(subscribers)):
            print("\nAborted.")
            sys.exit(0)
        
        # Ask for optional delay
        print("\n" + "-" * 60)
        print("OPTIONAL DELAY")
        print("-" * 60)
        print("Enter a delay in seconds (0 = send immediately)")
        print("Examples: 0 (now), 3600 (1 hour), 7200 (2 hours), 43200 (12 hours)")
        
        while True:
            try:
                delay_input = input("\nDelay in seconds [0]: ").strip()
                if delay_input == "":
                    delay_seconds = 0
                else:
                    delay_seconds = int(delay_input)
                    if delay_seconds < 0:
                        print("Error: Delay must be 0 or positive")
                        continue
                break
            except ValueError:
                print("Error: Please enter a valid number")
        
        # Wait if delay specified
        if delay_seconds > 0:
            wait_with_wakelock(delay_seconds)
    
    # Send newsletter
    success, failed = send_newsletter(html_path, subscribers, args.dry_run)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Successful: {success}")
    print(f"Failed: {failed}")
    
    if not args.dry_run and success > 0:
        print("\n" + "-" * 60)
        print("REMINDER: Upload the HTML file for 'View in Browser' link")
        print(f"  File: {html_path.name}")
        print("  Upload to: https://static.philippdubach.com/newsletter/")
        print("-" * 60)


if __name__ == "__main__":
    main()