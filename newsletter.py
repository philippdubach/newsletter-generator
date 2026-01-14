#!/usr/bin/env python3
"""
Newsletter Generator for philippdubach.com

Converts Markdown newsletters to email-safe HTML with automatic
OpenGraph metadata fetching for link preview cards.

Usage:
    python newsletter.py example.md
    python newsletter.py example.md --output custom_output.html
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
import calendar

import requests
from bs4 import BeautifulSoup

# Cache directory for OpenGraph data
CACHE_DIR = Path(__file__).parent / ".og_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Input directory
INPUT_DIR = Path(__file__).parent / "input"
INPUT_DIR.mkdir(exist_ok=True)

# Output directory
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Request timeout and headers
REQUEST_TIMEOUT = 10
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def get_cache_path(url: str) -> Path:
    """Generate a cache file path for a URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.json"


def fetch_opengraph(url: str) -> dict:
    """
    Fetch OpenGraph metadata from a URL.
    Returns dict with title, description, image, and site_name.
    Uses local cache to avoid repeated requests.
    """
    cache_path = get_cache_path(url)
    
    # Check cache first
    if cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    og_data = {
        "url": url,
        "title": "",
        "description": "",
        "image": "",
        "site_name": ""
    }
    
    try:
        response = requests.get(
            url, 
            headers=REQUEST_HEADERS, 
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract OpenGraph tags
        og_tags = {
            "title": ["og:title", "twitter:title"],
            "description": ["og:description", "twitter:description"],
            "image": ["og:image", "twitter:image"],
            "site_name": ["og:site_name"]
        }
        
        for key, tag_names in og_tags.items():
            for tag_name in tag_names:
                meta = soup.find("meta", property=tag_name) or soup.find("meta", attrs={"name": tag_name})
                if meta and meta.get("content"):
                    og_data[key] = meta["content"]
                    break
        
        # Fallback to <title> tag if no og:title
        if not og_data["title"]:
            title_tag = soup.find("title")
            if title_tag:
                og_data["title"] = title_tag.get_text().strip()
        
        # Fallback to meta description
        if not og_data["description"]:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                og_data["description"] = meta_desc["content"]
        
        # Extract site name from URL if not found
        if not og_data["site_name"]:
            parsed = urlparse(url)
            og_data["site_name"] = parsed.netloc
        
        # Make image URL absolute
        if og_data["image"] and not og_data["image"].startswith("http"):
            og_data["image"] = urljoin(url, og_data["image"])
        
        # Cache the result
        with open(cache_path, "w") as f:
            json.dump(og_data, f, indent=2)
        
        print(f"  ✓ Fetched: {og_data['title'][:50]}...")
        
    except requests.RequestException as e:
        print(f"  ✗ Failed to fetch {url}: {e}")
        og_data["title"] = urlparse(url).path.split("/")[-1] or url
        og_data["site_name"] = urlparse(url).netloc
    
    return og_data


def is_philippdubach_url(url: str) -> bool:
    """Check if URL is for philippdubach.com or any subdomain."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return domain == "philippdubach.com" or domain.endswith(".philippdubach.com")


def add_ref_param(url: str, ref: str) -> str:
    """Add ref and campaign parameters to URL for tracking."""
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    query_params["ref"] = [ref]
    query_params["campaign"] = [ref]
    new_query = urlencode(query_params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def optimize_image_url(image_url: str, width: int = 240, quality: int = 80) -> str:
    """
    Optimize image URL using Cloudflare CDN for static.philippdubach.com images.
    For email, we use 240px width (2x the display size of 120px for retina).
    """
    if not image_url:
        return image_url
    
    # Only optimize images from static.philippdubach.com
    if "static.philippdubach.com" not in image_url:
        return image_url
    
    # If already optimized, return as-is
    if "/cdn-cgi/image/" in image_url:
        return image_url
    
    # Extract the path from the URL
    parsed = urlparse(image_url)
    path = parsed.path
    
    # Remove leading slash if present for CDN path
    if path.startswith("/"):
        path = path[1:]
    
    # Build optimized URL using Cloudflare's image optimization
    base_url = "https://static.philippdubach.com"
    optimized_url = f"{base_url}/cdn-cgi/image/width={width},quality={quality},format=webp/{path}"
    
    return optimized_url


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from markdown content."""
    frontmatter = {}
    body = content
    
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if match:
        fm_text = match.group(1)
        body = content[match.end():]
        
        for line in fm_text.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip()
    
    return frontmatter, body


def parse_sections(body: str) -> dict:
    """Parse markdown body into sections based on # headers."""
    sections = {}
    current_section = None
    current_content = []
    
    for line in body.split("\n"):
        header_match = re.match(r"^#\s+(.+)$", line)
        if header_match:
            if current_section:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = header_match.group(1).lower()
            current_content = []
        else:
            current_content.append(line)
    
    if current_section:
        sections[current_section] = "\n".join(current_content).strip()
    
    return sections


def parse_link_list(content: str) -> list[dict]:
    """
    Parse a list of URLs from markdown content.
    Returns list of dicts with 'url', 'custom_title', and 'custom_description'.
    
    Supports formats:
    - https://example.com                        → use OG title + OG description
    - https://example.com - Custom description   → use OG title + custom description
    - [Custom Title](https://example.com)        → use custom title + OG description
    - [Custom Title](https://example.com) - Desc → use custom title + custom description
    """
    items = []
    
    def _strip_leading_separator(text: str) -> str:
        # Accept common separators including various unicode dashes.
        return re.sub(r"^[\s\u00A0]*[-–—:‑‒−‐][\s\u00A0]*", "", text).strip()
    
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("-"):
            line = line[1:].strip()
        
        if not line:
            continue
        
        custom_title = ""
        custom_description = ""
        
        # Check for markdown link first: [text](url) optionally followed by - description
        md_match = re.match(r"\[([^\]]*)\]\((https?://[^\)]+)\)", line)
        if md_match:
            custom_title = md_match.group(1).strip()
            url = md_match.group(2)
            rest = line[md_match.end():].strip()
            custom_description = _strip_leading_separator(rest) if rest else ""
            items.append({"url": url, "custom_title": custom_title, "custom_description": custom_description})
            continue
        
        # Check for bare URL optionally followed by - description
        if line.startswith("http"):
            parts = line.split(maxsplit=1)
            url = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            custom_description = _strip_leading_separator(rest) if rest else ""
            items.append({"url": url, "custom_title": "", "custom_description": custom_description})
    
    return items


def parse_reading_list(content: str) -> list[dict]:
    """Parse reading list with optional descriptions."""
    items = []

    def _strip_leading_separator(text: str) -> str:
        # Accept common separators including various unicode dashes.
        # Examples:
        #   "- note" / "– note" / "— note" / ": note"
        #   " - note" (with spaces)
        return re.sub(r"^[\s\u00A0]*[-–—:‑‒−‐][\s\u00A0]*", "", text).strip()

    for line in content.split("\n"):
        line = line.strip()
        if not line or not line.startswith("-"):
            continue
        
        line = line[1:].strip()
        
        # Parse markdown link with optional description
        match = re.match(r"\[(.+?)\]\((https?://[^\)]+)\)", line)
        if match:
            rest = _strip_leading_separator(line[match.end():]) if len(line) > match.end() else ""
            items.append(
                {
                    "title": match.group(1),
                    "url": match.group(2),
                    "description": rest,
                }
            )
            continue

        # Bare URL with optional description
        if line.startswith("http"):
            parts = line.split(maxsplit=1)
            url = parts[0]
            rest = _strip_leading_separator(parts[1]) if len(parts) > 1 else ""
            items.append(
                {
                    "title": url,
                    "url": url,
                    "description": rest,
                }
            )
            continue
    
    return items


def render_card(og_data: dict, ref: str, is_first: bool = False, custom_title: str = None, custom_description: str = None) -> str:
    """Render a LinkedIn-style link preview card with image on left.
    
    Args:
        og_data: OpenGraph data dict with url, title, description, image, site_name
        ref: Reference tag for tracking
        is_first: Whether this is the first card (no top margin)
        custom_title: Optional custom title to override og_data title
        custom_description: Optional custom description to override og_data description
    """
    url = add_ref_param(og_data["url"], ref)
    title = custom_title if custom_title else (og_data["title"] or og_data["url"])
    description = custom_description if custom_description else og_data["description"]
    image = og_data["image"]
    site_name = og_data["site_name"]
    
    # Optimize image URL if from static.philippdubach.com
    if image:
        image = optimize_image_url(image, width=240, quality=80)
    
    # Truncate description
    if len(description) > 150:
        description = description[:147] + "..."
    
    # First card has no top margin
    margin_style = "margin: 0 0 12px 0;" if is_first else "margin: 12px 0;"
    
    # Alt text for accessibility
    alt_text = f"Preview image for: {title[:50]}" if title else "Article preview"
    
    image_html = ""
    if image:
        image_html = f'''
                <!--[if mso]>
                <td width="120" valign="top" style="padding: 12px 0 12px 12px;">
                <![endif]-->
                <!--[if !mso]><!-->
                <td class="card-image" width="120" style="padding: 12px 0 12px 12px; vertical-align: top;">
                <!--<![endif]-->
                    <a href="{url}" style="text-decoration: none; display: block;">
                        <img src="{image}" alt="{alt_text}" width="120" height="auto"
                             style="display: block; width: 120px; max-width: 100%; height: auto; border-radius: 4px; border: 0;">
                    </a>
                </td>'''
    
    return f'''
        <table cellpadding="0" cellspacing="0" border="0" width="100%" role="presentation"
               style="{margin_style} background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 8px;">
            <tr>{image_html}
                <td class="card-content" style="padding: 12px 14px; vertical-align: top;">
                    <a href="{url}" style="text-decoration: none; display: block;">
                        <div style="font-weight: 600; font-size: 15px; line-height: 1.4; margin-bottom: 6px; color: #333333;">
                            {title}
                        </div>
                    </a>
                    <div style="font-size: 15px; color: #666666; line-height: 1.75;">
                        {description}
                    </div>
                </td>
            </tr>
        </table>'''


def render_reading_item(item: dict, ref: str) -> str:
    """Render a reading list item as a bullet point."""
    url = add_ref_param(item["url"], ref)
    title = item["title"]
    description = item.get("description", "")
    
    # Extract source domain for attribution
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()
    
    # Map common domains to readable names
    source_map = {
        "arxiv.org": "arXiv",
        "papers.ssrn.com": "SSRN",
        "github.com": "GitHub",
        "medium.com": "Medium",
        "substack.com": "Substack",
    }
    
    source = source_map.get(domain, domain.replace("www.", "").split(".")[0].title())
    if domain.startswith("arxiv"):
        source = "arXiv"
    elif "ssrn" in domain:
        source = "SSRN"
    
    desc_html = ""
    if description:
        desc_html = f': <span style="color: #666666;">{description}</span>'
    
    return f'''
        <tr>
            <td style="padding: 3px 0; font-size: 14px; line-height: 1.75; color: #333333;">
                <span style="font-size: 6px; vertical-align: middle;">&#9632;</span>&nbsp;&nbsp;
                <a href="{url}" style="color: #007acc; text-decoration: none;">{title}</a>{desc_html}
                <span style="color: #999999; font-size: 12px;"> via {source}</span>
            </td>
        </tr>'''


def render_section_header(title: str) -> str:
    """Render a section header."""
    return f'''
        <tr>
            <td style="padding: 28px 0 12px 0;">
                <h2 style="margin: 0; font-size: 15px; font-weight: 700; color: #333333; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                    {title}
                </h2>
            </td>
        </tr>'''


def render_text_content(text: str, ref: str = None) -> str:
    """Render free-form text content with basic markdown support."""
    
    def replace_link(match):
        """Replace markdown link, adding tracking params for philippdubach.com URLs."""
        link_text = match.group(1)
        url = match.group(2)
        # Add tracking params if it's a philippdubach.com URL and ref is provided
        if ref and not url.startswith("mailto:") and is_philippdubach_url(url):
            url = add_ref_param(url, ref)
        return f'<a href="{url}" style="color: #007acc; text-decoration: none;">{link_text}</a>'
    
    # Convert markdown paragraphs to HTML
    paragraphs = text.strip().split("\n\n")
    html_parts = []
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Convert markdown links (with tracking for philippdubach.com)
        para = re.sub(
            r"\[(.+?)\]\(((?:https?://|mailto:)[^\)]+)\)",
            replace_link,
            para
        )
        
        # Convert bold
        para = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", para)
        
        # Convert italic
        para = re.sub(r"\*(.+?)\*", r"<em>\1</em>", para)
        
        html_parts.append(f'''
        <tr>
            <td style="padding: 8px 0; font-size: 15px; line-height: 1.75; color: #333333;">
                {para}
            </td>
        </tr>''')
    
    return "\n".join(html_parts)


def generate_newsletter(md_path: Path, output_path: Path = None) -> Path:
    """Generate HTML newsletter from markdown file."""
    print(f"\n📧 Generating newsletter from {md_path.name}\n")
    
    content = md_path.read_text()
    frontmatter, body = parse_frontmatter(content)
    sections = parse_sections(body)
    
    # Extract metadata
    date = frontmatter.get("date", datetime.now().strftime("%Y-%m"))
    title = frontmatter.get("title", "What you missed")
    greeting = frontmatter.get("greeting", "")
    ref = f"newsletter-{date}"
    
    # Format date as "December 2025"
    try:
        year, month = date.split("-")
        date_display = f"{calendar.month_name[int(month)]} {year}"
    except (ValueError, IndexError):
        date_display = date
    
    print(f"Date: {date_display}")
    print(f"Title: {title}")
    print(f"Ref tag: {ref}\n")
    
    # Build HTML sections
    html_sections = []
    
    # Greeting
    if greeting:
        html_sections.append(f'''
        <tr>
            <td class="dark-text" style="padding: 0 0 8px 0; font-size: 18px; font-weight: 600; color: #333333;">
                {greeting}
            </td>
        </tr>''')
    
    # Introduction
    if "introduction" in sections:
        html_sections.append(render_text_content(sections["introduction"], ref))
    
    # What I've been writing
    if "writing" in sections:
        print("Fetching OpenGraph data for Writing section...")
        items = parse_link_list(sections["writing"])
        if items:
            html_sections.append(render_section_header("What I've been writing"))
            html_sections.append('<tr><td>')
            for i, item in enumerate(items):
                og_data = fetch_opengraph(item["url"])
                custom_title = item.get("custom_title") or None
                custom_description = item.get("custom_description") or None
                html_sections.append(render_card(og_data, ref, is_first=(i == 0), custom_title=custom_title, custom_description=custom_description))
            html_sections.append('</td></tr>')
    
    # What I've been working on
    if "working" in sections:
        print("\nFetching OpenGraph data for Working section...")
        items = parse_link_list(sections["working"])
        if items:
            html_sections.append(render_section_header("What I've been working on"))
            html_sections.append('<tr><td>')
            for i, item in enumerate(items):
                og_data = fetch_opengraph(item["url"])
                custom_title = item.get("custom_title") or None
                custom_description = item.get("custom_description") or None
                html_sections.append(render_card(og_data, ref, is_first=(i == 0), custom_title=custom_title, custom_description=custom_description))
            html_sections.append('</td></tr>')
    
    # What I've been reading
    if "reading" in sections:
        print("\nProcessing Reading section...")
        items = parse_reading_list(sections["reading"])
        if items:
            html_sections.append(render_section_header("What I've been reading"))
            html_sections.append('<tr><td><table cellpadding="0" cellspacing="0" border="0" width="100%">')
            for item in items:
                html_sections.append(render_reading_item(item, ref))
            html_sections.append('</table></td></tr>')
    
    # Closing
    if "closing" in sections:
        html_sections.append('<tr><td style="padding-top: 16px;"></td></tr>')
        html_sections.append(render_text_content(sections["closing"], ref))
    
    # Combine all sections
    body_content = "\n".join(html_sections)
    
    # Generate preheader text from introduction (first 100 chars)
    preheader = ""
    if "introduction" in sections:
        intro_text = sections["introduction"].strip()
        # Remove markdown formatting for preheader
        intro_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', intro_text)
        intro_text = re.sub(r'\*+([^*]+)\*+', r'\1', intro_text)
        preheader = intro_text[:150].replace('\n', ' ').strip()
        if len(intro_text) > 150:
            preheader += "..."
    
    # Generate full HTML
    html = f'''<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="x-apple-disable-message-reformatting">
    <meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no">
    <meta name="color-scheme" content="light only">
    <meta name="supported-color-schemes" content="light only">
    <title>{title}</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:AllowPNG/>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style type="text/css">
        /* Force light mode in all clients */
        :root {{ color-scheme: light only; }}
        
        /* Reset and base styles */
        body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
        
        /* Prevent Gmail from adding spacing */
        .ExternalClass {{ width: 100%; }}
        .ExternalClass, .ExternalClass p, .ExternalClass span, .ExternalClass font, .ExternalClass td, .ExternalClass div {{ line-height: 100%; }}
        
        /* Responsive styles */
        @media screen and (max-width: 600px) {{
            .wrapper {{ width: 100% !important; max-width: 100% !important; }}
            .mobile-padding {{ padding-left: 16px !important; padding-right: 16px !important; }}
            .card-content {{ padding: 10px 12px !important; }}
            .mobile-full-width {{ width: 100% !important; }}
        }}
        
        /* Prevent dark mode color inversion */
        @media (prefers-color-scheme: dark) {{
            body, .body-wrapper, .content-wrapper, .card-wrapper {{
                background-color: #ffffff !important;
            }}
            h1, h2, h3, p, td, span, div, a {{
                color: inherit !important;
            }}
        }}
        
        /* Prevent Outlook.com dark mode */
        [data-ogsc] body,
        [data-ogsc] .body-wrapper,
        [data-ogsc] .content-wrapper {{
            background-color: #ffffff !important;
        }}
    </style>
</head>
<body class="body-wrapper" style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;">
    <!-- Preheader text (hidden preview text) -->
    <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;" aria-hidden="true">
        {preheader}
        &#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;
    </div>
    <!-- Wrapper table for centering -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" class="body-wrapper" style="background-color: #ffffff; margin: 0; padding: 0;">
        <tr>
            <td align="center" style="padding: 0; margin: 0;">
                <!--[if mso]>
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" align="center">
                <tr>
                <td>
                <![endif]-->
                <table class="wrapper content-wrapper" role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width: 600px; width: 100%; margin: 0 auto; background-color: #ffffff;">
                    <!-- View in Browser -->
                    <tr>
                        <td class="mobile-padding" align="center" style="padding: 20px 20px 16px 20px;">
                            <a href="https://static.philippdubach.com/newsletter/newsletter-{date}.html" style="font-size: 12px; color: #999999; text-decoration: none;">
                                View in browser
                            </a>
                        </td>
                    </tr>
                    
                    <!-- Header -->
                    <tr>
                        <td class="mobile-padding" style="padding: 0 20px 20px 20px; border-bottom: 1px solid #e9ecef;">
                            <a href="https://philippdubach.com?ref={ref}&campaign={ref}" style="text-decoration: none; display: inline-block;">
                                <img src="https://philippdubach.com/icons/favicon-96x96.png" alt="philippdubach.com" width="20" height="20" 
                                     style="display: inline-block; width: 20px; height: 20px; vertical-align: middle; margin-right: 6px; border-radius: 4px; border: 0;">
                                <span style="font-size: 18px; font-weight: 700; color: #333333; vertical-align: middle;">philippdubach</span>
                            </a>
                            <p style="margin: 6px 0 0 0; font-size: 13px; color: #666666;">
                                {date_display}: {title}
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td class="mobile-padding" style="padding: 24px 20px 0 20px;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                                {body_content}
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td class="mobile-padding" style="padding: 24px 20px 20px 20px; border-top: 1px solid #e9ecef;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                                <tr>
                                    <td align="center" style="padding: 12px 0 6px 0; font-size: 13px; color: #666666; line-height: 1.5;">
                                        Have feedback, comments, or ideas? I'd love to hear from you: 
                                        <a href="mailto:me@philippdubach.com" style="color: #007acc; text-decoration: none;">me@philippdubach.com</a>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding: 4px 0; font-size: 13px; color: #666666;">
                                        <a href="https://philippdubach.com?ref={ref}&campaign={ref}" style="color: #666666; text-decoration: none;">Blog</a>
                                        <span style="color: #999999;">&nbsp;|&nbsp;</span>
                                        <a href="https://philippdubach.com/projects/?ref={ref}&campaign={ref}" style="color: #666666; text-decoration: none;">Projects</a>
                                        <span style="color: #999999;">&nbsp;|&nbsp;</span>
                                        <a href="https://philippdubach.com/research/?ref={ref}&campaign={ref}" style="color: #666666; text-decoration: none;">Research</a>
                                        <span style="color: #999999;">&nbsp;|&nbsp;</span>
                                        <a href="https://github.com/philippdubach?ref={ref}&campaign={ref}" style="color: #666666; text-decoration: none;">GitHub</a>
                                        <span style="color: #999999;">&nbsp;|&nbsp;</span>
                                        <a href="https://bsky.app/profile/philippdubach.com" style="color: #666666; text-decoration: none;">Bluesky</a>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding: 6px 0 0 0; font-size: 11px; color: #999999;">
                                        Reply to unsubscribe
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
                <!--[if mso]>
                </td>
                </tr>
                </table>
                <![endif]-->
            </td>
        </tr>
    </table>
</body>
</html>'''
    
    # Determine output path
    if output_path is None:
        output_path = OUTPUT_DIR / f"newsletter-{date}.html"
    
    output_path.write_text(html)
    print(f"\n✅ Newsletter generated: {output_path}")
    print(f"   Open in browser to preview, then copy HTML for your email client.\n")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML newsletter from Markdown"
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Path to markdown newsletter file (default: looks in input/ folder)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output HTML file path (default: output/newsletter-DATE.html)"
    )
    
    args = parser.parse_args()
    
    # If no input specified, find the most recent .md file in input/
    if args.input is None:
        md_files = sorted(INPUT_DIR.glob("newsletter-*.md"), reverse=True)
        if not md_files:
            print(f"Error: No newsletter-*.md files found in {INPUT_DIR}")
            sys.exit(1)
        args.input = md_files[0]
        print(f"Using: {args.input}")
    
    # Check if input exists, also try input/ folder
    if not args.input.exists():
        alt_path = INPUT_DIR / args.input
        if alt_path.exists():
            args.input = alt_path
        else:
            print(f"Error: Input file not found: {args.input}")
            sys.exit(1)
    
    generate_newsletter(args.input, args.output)


if __name__ == "__main__":
    main()

