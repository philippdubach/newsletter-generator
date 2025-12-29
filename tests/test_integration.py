"""Integration tests for newsletter generation."""

import tempfile
from pathlib import Path

from newsletter import generate_newsletter, OUTPUT_DIR


class TestGenerateNewsletter:
    def test_generates_html_output(self, tmp_path):
        md_content = """---
date: 2025-01
title: Test Newsletter
greeting: Hello!
---

# Introduction
This is a test newsletter.

# Closing
Thanks for reading.
"""
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content)
        
        output_file = tmp_path / "output.html"
        result = generate_newsletter(md_file, output_file)
        
        assert result.exists()
        html = result.read_text()
        
        assert "Test Newsletter" in html
        assert "January 2025" in html
        assert "Hello!" in html
        assert "This is a test newsletter." in html

    def test_uses_default_output_path(self, tmp_path):
        md_content = """---
date: 2025-02
title: February Newsletter
---

# Introduction
Content here.
"""
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content)
        
        result = generate_newsletter(md_file)
        
        assert "newsletter-2025-02.html" in str(result)
        assert result.exists()
        
        # Cleanup
        result.unlink()

    def test_handles_missing_optional_sections(self, tmp_path):
        md_content = """---
date: 2025-03
title: Minimal Newsletter
---

# Introduction
Just an intro.
"""
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content)
        
        output_file = tmp_path / "minimal.html"
        result = generate_newsletter(md_file, output_file)
        
        assert result.exists()
        html = result.read_text()
        assert "Just an intro." in html
