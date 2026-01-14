# newsletter-generator

A Python CLI tool that converts Markdown newsletters into email-safe HTML. It fetches OpenGraph metadata from links and renders them as preview cards, similar to how LinkedIn displays shared articles.

I built this for my personal website [philippdubach.com](https://philippdubach.com) but it should work for any newsletter workflow where you want nice link previews without manual HTML editing.

## What it does

- Parses markdown files with frontmatter (date, title, greeting)
- Fetches OpenGraph data (title, description, image) from URLs in your content
- Generates table-based HTML that works in most email clients
- Caches OpenGraph results locally so you dont hammer external sites
- Adds ref tracking parameters to all outbound links

## Installation

```bash
git clone https://github.com/philippdubach/newsletter-generator.git
cd newsletter-generator
pip install -r requirements.txt
```

## Usage

Put your markdown files in `input/` and run:

```bash
python newsletter.py
```

This picks up the most recent `newsletter-*.md` file from the input folder. You can also specify a file directly:

```bash
python newsletter.py input/newsletter-2025-12.md
python newsletter.py somefile.md --output custom.html
```

Output goes to `output/newsletter-YYYY-MM.html`.

## Markdown format

```markdown
---
date: 2025-01
title: January Update
greeting: Happy New Year!
---

# Introduction
Some intro text here. Supports **bold** and *italic*.

# Writing
- https://example.com/your-article

# Working
- https://github.com/username/project

# Reading
- [Paper Title](https://arxiv.org/abs/1234) - Optional description

# Closing
Sign off text.
```

The sections are optional. Writing and Working sections render as preview cards with images. Reading renders as a bulleted list with source attribution.

## How the caching works

First time you process a URL, the tool fetches its OpenGraph metadata and stores it in `.og_cache/`. Subsequent runs use the cached data. Delete the cache files if you need fresh data.

## Testing

```bash
pytest tests/
```

## Project structure

```
newsletter-generator/
├── newsletter.py       # Main script
├── requirements.txt    # Dependencies
├── input/              # Markdown source files
│   └── template.md     # Template for new newsletters
├── output/             # Generated HTML (gitignored)
├── tests/              # Test suite
└── .og_cache/          # OpenGraph cache (gitignored)
```

## License

MIT

