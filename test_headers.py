#!/usr/bin/env python3
"""
Test script to verify exact headers being sent
"""
import hashlib
from pathlib import Path

# Simulate what send.py does
html_path = Path("output/newsletter-2026-01.html")
subscriber_email = "test@example.com"
REPLY_TO = "me@philippdubach.com"

# Generate token same way as send.py
token_data = f"{subscriber_email}:{html_path.stem}"
token = hashlib.sha256(token_data.encode()).hexdigest()[:32]

print("Token:", token)
print("\nHeaders that will be sent:")
print(f'List-Unsubscribe: <https://philippdubach.com/api/unsubscribe?token={token}>, <mailto:{REPLY_TO}?subject=Unsubscribe>')
print(f'List-Unsubscribe-Post: List-Unsubscribe=One-Click')
print(f'List-Id: philippdubach.com Newsletter <newsletter.philippdubach.com>')
print(f'Precedence: bulk')
print(f'Auto-Submitted: auto-generated')

print("\nTesting POST endpoint:")
import subprocess
result = subprocess.run([
    'curl', '-s', '-w', '\\nHTTP Status: %{http_code}', '-X', 'POST',
    f'https://philippdubach.com/api/unsubscribe?token={token}',
    '-H', 'Content-Type: application/x-www-form-urlencoded',
    '-d', 'List-Unsubscribe=One-Click'
], capture_output=True, text=True)
print(result.stdout)
