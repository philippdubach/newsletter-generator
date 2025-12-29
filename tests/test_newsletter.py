"""Tests for newsletter.py"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from newsletter import (
    parse_frontmatter,
    parse_sections,
    parse_link_list,
    parse_reading_list,
    add_ref_param,
    optimize_image_url,
    render_text_content,
    get_cache_path,
    fetch_opengraph,
    CACHE_DIR,
)


class TestParseFrontmatter:
    def test_basic_frontmatter(self):
        content = """---
date: 2025-01
title: Test Newsletter
greeting: Hello!
---

# Introduction
Body content here."""
        
        fm, body = parse_frontmatter(content)
        
        assert fm["date"] == "2025-01"
        assert fm["title"] == "Test Newsletter"
        assert fm["greeting"] == "Hello!"
        assert "# Introduction" in body
        assert "Body content here." in body

    def test_no_frontmatter(self):
        content = """# Introduction
Just body content."""
        
        fm, body = parse_frontmatter(content)
        
        assert fm == {}
        assert body == content

    def test_empty_frontmatter(self):
        content = """---
---

# Body"""
        
        fm, body = parse_frontmatter(content)
        
        assert fm == {}
        assert "# Body" in body


class TestParseSections:
    def test_multiple_sections(self):
        body = """# Introduction
Intro text here.

# Writing
- https://example.com/article

# Reading
- [Link](https://example.com)"""
        
        sections = parse_sections(body)
        
        assert "introduction" in sections
        assert "writing" in sections
        assert "reading" in sections
        assert "Intro text here." in sections["introduction"]
        assert "https://example.com/article" in sections["writing"]

    def test_empty_body(self):
        sections = parse_sections("")
        assert sections == {}

    def test_no_sections(self):
        body = "Just plain text without headers."
        sections = parse_sections(body)
        assert sections == {}


class TestParseLinkList:
    def test_bare_urls(self):
        content = """- https://example.com/one
- https://example.com/two"""
        
        urls = parse_link_list(content)
        
        assert len(urls) == 2
        assert urls[0] == "https://example.com/one"
        assert urls[1] == "https://example.com/two"

    def test_markdown_links(self):
        content = """- [Title](https://example.com/one)
- [Another](https://example.com/two)"""
        
        urls = parse_link_list(content)
        
        assert len(urls) == 2
        assert urls[0] == "https://example.com/one"

    def test_mixed_links(self):
        content = """- https://example.com/bare
- [Markdown](https://example.com/markdown)"""
        
        urls = parse_link_list(content)
        
        assert len(urls) == 2

    def test_empty_content(self):
        urls = parse_link_list("")
        assert urls == []


class TestParseReadingList:
    def test_with_descriptions(self):
        content = """- [Article](https://example.com) - Great read
- [Paper](https://arxiv.org/abs/123) - Important findings"""
        
        items = parse_reading_list(content)
        
        assert len(items) == 2
        assert items[0]["title"] == "Article"
        assert items[0]["url"] == "https://example.com"
        assert items[0]["description"] == "Great read"

    def test_without_descriptions(self):
        content = "- [Article](https://example.com)"
        
        items = parse_reading_list(content)
        
        assert len(items) == 1
        assert items[0]["description"] == ""

    def test_bare_url(self):
        content = "- https://example.com/bare"
        
        items = parse_reading_list(content)
        
        assert len(items) == 1
        assert items[0]["url"] == "https://example.com/bare"


class TestAddRefParam:
    def test_adds_ref_to_clean_url(self):
        url = "https://example.com/page"
        result = add_ref_param(url, "newsletter-2025-01")
        
        assert "ref=newsletter-2025-01" in result

    def test_adds_ref_to_url_with_params(self):
        url = "https://example.com/page?existing=param"
        result = add_ref_param(url, "test")
        
        assert "existing=param" in result
        assert "ref=test" in result

    def test_preserves_path(self):
        url = "https://example.com/path/to/page"
        result = add_ref_param(url, "ref")
        
        assert "/path/to/page" in result


class TestOptimizeImageUrl:
    def test_optimizes_static_philippdubach_images(self):
        url = "https://static.philippdubach.com/images/test.jpg"
        result = optimize_image_url(url)
        
        assert "/cdn-cgi/image/" in result
        assert "width=240" in result
        assert "quality=80" in result
        assert "format=webp" in result

    def test_ignores_external_images(self):
        url = "https://example.com/image.jpg"
        result = optimize_image_url(url)
        
        assert result == url

    def test_ignores_already_optimized(self):
        url = "https://static.philippdubach.com/cdn-cgi/image/width=100/test.jpg"
        result = optimize_image_url(url)
        
        assert result == url

    def test_handles_empty_url(self):
        assert optimize_image_url("") == ""

    def test_custom_dimensions(self):
        url = "https://static.philippdubach.com/test.jpg"
        result = optimize_image_url(url, width=500, quality=90)
        
        assert "width=500" in result
        assert "quality=90" in result


class TestRenderTextContent:
    def test_converts_markdown_links(self):
        text = "Check out [this link](https://example.com)."
        result = render_text_content(text)
        
        assert '<a href="https://example.com"' in result
        assert "this link</a>" in result

    def test_converts_bold(self):
        text = "This is **bold** text."
        result = render_text_content(text)
        
        assert "<strong>bold</strong>" in result

    def test_converts_italic(self):
        text = "This is *italic* text."
        result = render_text_content(text)
        
        assert "<em>italic</em>" in result

    def test_handles_paragraphs(self):
        text = """First paragraph.

Second paragraph."""
        result = render_text_content(text)
        
        assert "First paragraph." in result
        assert "Second paragraph." in result


class TestCaching:
    def test_cache_path_is_deterministic(self):
        url = "https://example.com/test"
        path1 = get_cache_path(url)
        path2 = get_cache_path(url)
        
        assert path1 == path2

    def test_different_urls_have_different_paths(self):
        path1 = get_cache_path("https://example.com/one")
        path2 = get_cache_path("https://example.com/two")
        
        assert path1 != path2


class TestFetchOpengraph:
    @patch("newsletter.requests.get")
    def test_fetches_og_data(self, mock_get):
        html = """
        <html>
        <head>
            <meta property="og:title" content="Test Title">
            <meta property="og:description" content="Test Description">
            <meta property="og:image" content="https://example.com/image.jpg">
            <meta property="og:site_name" content="Example">
        </head>
        </html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        # Use a temp directory for cache
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("newsletter.CACHE_DIR", Path(tmpdir)):
                og_data = fetch_opengraph("https://example.com/test")
        
        assert og_data["title"] == "Test Title"
        assert og_data["description"] == "Test Description"
        assert og_data["image"] == "https://example.com/image.jpg"

    @patch("newsletter.requests.get")
    def test_falls_back_to_title_tag(self, mock_get):
        html = """
        <html>
        <head>
            <title>Page Title</title>
        </head>
        </html>
        """
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("newsletter.CACHE_DIR", Path(tmpdir)):
                og_data = fetch_opengraph("https://example.com/test")
        
        assert og_data["title"] == "Page Title"

    @patch("newsletter.requests.get")
    def test_handles_request_failure(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("Connection failed")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("newsletter.CACHE_DIR", Path(tmpdir)):
                og_data = fetch_opengraph("https://example.com/fail")
        
        assert og_data["url"] == "https://example.com/fail"
        assert og_data["site_name"] == "example.com"

    def test_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            test_url = "https://cached.example.com/page"
            
            # Create cache file
            with patch("newsletter.CACHE_DIR", cache_dir):
                cache_path = get_cache_path(test_url)
            
            cache_data = {
                "url": test_url,
                "title": "Cached Title",
                "description": "Cached Desc",
                "image": "",
                "site_name": "cached.example.com"
            }
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache_data))
            
            with patch("newsletter.CACHE_DIR", cache_dir):
                og_data = fetch_opengraph(test_url)
            
            assert og_data["title"] == "Cached Title"
