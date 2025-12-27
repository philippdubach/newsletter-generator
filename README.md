# Newsletter Generator for philippdubach.com

A Python tool that converts Markdown newsletters into email-safe HTML with automatic OpenGraph metadata fetching for beautiful link preview cards.

## Features

- ✨ **Markdown-based**: Write newsletters in simple Markdown
- 🎨 **Automatic link previews**: Fetches OpenGraph metadata (title, description, image) for links
- 📧 **Email-safe HTML**: Table-based layout with inline CSS for maximum email client compatibility
- 🎯 **Link tracking**: Automatically adds `?ref=newsletter-YYYY-MM` to all links
- 💾 **Caching**: OpenGraph data is cached locally to avoid repeated fetches
- 🎨 **Matches website design**: Styled to match philippdubach.com aesthetic

## Installation

1. Install Python dependencies:
```bash
pip3 install -r requirements.txt
```

## Quick Start

1. Edit `example.md` (or create your own `.md` file)
2. Run the generator:
```bash
python3 newsletter.py example.md
```
3. Preview the generated HTML in `output/newsletter-YYYY-MM.html`
4. Copy the HTML and paste into your email client

## Markdown Format

Your newsletter should follow this structure:

```markdown
---
date: 2025-12
title: What you missed
greeting: Happy New Year!
---

# Introduction
Your free-form introduction text here. You can use **bold** and *italic* formatting.

# Writing
- https://philippdubach.com/2025/12/15/article-one/
- https://philippdubach.com/2025/12/10/article-two/

# Working
- https://github.com/username/project-name

# Reading
- [Article Title](https://example.com/article) - Optional description
- [Another Article](https://example.com/another)

# Closing
Optional closing remarks...
```

### Front Matter

The YAML front matter at the top defines metadata:

- `date`: Newsletter date in `YYYY-MM` format (e.g., `2025-12`)
- `title`: Newsletter title (e.g., "What you missed")
- `greeting`: Optional greeting text (e.g., "Happy New Year!")

### Sections

- **Introduction**: Free-form text with Markdown support
- **Writing**: List of article URLs (2-5 recommended). These will be rendered as link preview cards with images
- **Working**: List of project URLs (1-2 recommended). Same card style as Writing
- **Reading**: List of links with optional descriptions. Rendered as bullet points with source attribution
- **Closing**: Optional free-form text

## Examples

### Basic Newsletter

```markdown
---
date: 2025-01
title: January Update
greeting: Happy New Year!
---

# Introduction
Welcome to the first newsletter of 2025! Here's what I've been up to.

# Writing
- https://philippdubach.com/2025/01/15/my-latest-article/

# Working
- https://github.com/philippdubach/my-project

# Reading
- [Interesting Paper](https://arxiv.org/abs/2401.00000) - A great read on machine learning
- [Another Link](https://example.com)
```

## Command Line Options

```bash
# Basic usage
python3 newsletter.py example.md

# Custom output file
python3 newsletter.py example.md --output my-newsletter.html

# Help
python3 newsletter.py --help
```

## How It Works

1. **Parse Markdown**: Reads your `.md` file and extracts sections
2. **Fetch OpenGraph Data**: For links in "Writing" and "Working" sections, fetches:
   - `og:title` or page title
   - `og:description` or meta description
   - `og:image` for preview thumbnail
   - `og:site_name` for source attribution
3. **Cache Results**: Saves OpenGraph data in `.og_cache/` to avoid re-fetching
4. **Generate HTML**: Creates email-safe HTML with:
   - Table-based layout
   - Inline CSS styles
   - Link preview cards (LinkedIn-style)
   - Bulleted reading list with source attribution
5. **Output**: Saves to `output/newsletter-YYYY-MM.html`

## File Structure

```
newsletter/
├── newsletter.py          # Main generator script
├── example.md            # Example newsletter
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── output/              # Generated HTML files
│   └── newsletter-2025-12.html
└── .og_cache/           # Cached OpenGraph data (auto-created)
```

## Features Explained

### Link Preview Cards

Links in "Writing" and "Working" sections are automatically converted to preview cards with:
- Thumbnail image (from OpenGraph metadata)
- Article title
- Description/excerpt
- Clean, minimal design matching your website

### Source Attribution

Reading list items automatically show source attribution:
- `arxiv.org` → "via arXiv"
- `papers.ssrn.com` → "via SSRN"
- `github.com` → "via GitHub"
- Other domains show the domain name

### Link Tracking

All links automatically get a tracking parameter:
- `https://example.com/article` → `https://example.com/article?ref=newsletter-2025-12`

This helps you track newsletter-driven traffic.

## Troubleshooting

### OpenGraph data not fetching

- Check your internet connection
- Some sites block automated requests
- Check `.og_cache/` - cached data might be outdated (delete cache files to re-fetch)

### Images not showing

- Email clients may block external images
- Ensure OpenGraph images use HTTPS URLs
- Some email clients require images to be hosted on a CDN

### Styling issues in email

- Email clients strip many CSS features
- The generator uses table-based layout for maximum compatibility
- Test in multiple email clients (Gmail, Apple Mail, Outlook)

## Tips

- **Keep it simple**: Newsletter works best with 2-5 articles in Writing, 1-2 in Working
- **Use descriptions**: Add descriptions to Reading list items for context
- **Preview first**: Always preview the HTML before sending
- **Test links**: Verify all links work before sending
- **Cache management**: Delete `.og_cache/` files if OpenGraph data seems outdated

## License

This tool is for personal use with philippdubach.com.

