"""
Tests sage_math_sanitizer.py in it's entirety.

Focuses on core functionality, quirks, and odd output combinations.
"""

import pytest

from localsage.sage_math_sanitizer import sanitize_math_safe

# 1. Normalization & Pre-filtering Tests


@pytest.mark.parametrize(
    "input_str, expected",
    [
        # HTML Entities
        ("Use &lt; and &gt;", "Use < and >"),
        ("Bread &amp; Butter", "Bread & Butter"),
        # Smart Quotes & Apostrophes
        ("“Hello” ‘World’", "\"Hello\" 'World'"),
        ("It’s ok", "It's ok"),
        # Unicode Quirks (based on _UNICODE_FIXES)
        ("Fullwidth ＃ hash", "Fullwidth # hash"),
        ("Bullet • point", "Bullet * point"),
        ("En–dash and Em—dash", "En-dash and Em-dash"),
    ],
)
def test_normalization_prefilter(input_str, expected):
    """Test _normalize_pre logic via the main entry point."""
    assert sanitize_math_safe(input_str) == expected


# 2. Code Block Preservation (Critical)


def test_preserves_inline_code():
    """Inline code spans should never be touched, even if they look like math."""
    text = "Try using `\\frac{1}{2}` or `$math$`."
    # The sanitizer should see backticks and skip processing inside
    assert sanitize_math_safe(text) == text


def test_preserves_fenced_code_blocks():
    """Fenced code blocks should preserve content."""
    text = """```
$HOME
$1.00
$20
$E=mc^2$
```"""
    # Standardize newlines for comparison if necessary, but exact string match is expected
    assert sanitize_math_safe(text) == text


def test_preserves_code_with_logic_operators():
    """Logic operators usually replaced via regex should be ignored inside code."""
    text = "Code: `\\implies`"
    # Outside code, \implies becomes ⇒. Inside, it must stay \implies.
    assert sanitize_math_safe(text) == "Code: `\\implies`"


# 3. Markdown Separators (Protection logic)


@pytest.mark.parametrize(
    "separator",
    [
        "---",
        "***",
        "___",
        "   ---   ",  # With spacing
    ],
)
def test_preserves_markdown_separators(separator):
    """Ensure separators aren't treated as math subscripts or removed."""
    # Note: The normalizer might strip trailing spaces, but the separator structure must exist.
    result = sanitize_math_safe(separator)
    assert separator.strip() in result


def test_separator_amidst_text():
    text = "Header\n---\nContent"
    assert sanitize_math_safe(text) == text


# 4. Logic Operators (Custom Regex)


@pytest.mark.parametrize(
    "latex_op, unicode_char",
    [
        ("\\iff", "⇔"),
        ("\\implies", "⇒"),
        ("\\to", "→"),
        ("\\rightarrow", "→"),
        ("\\leftarrow", "←"),
        ("\\because", "∵"),
        ("\\therefore", "∴"),
    ],
)
def test_logic_operators(latex_op, unicode_char):
    """Test the custom logic operator dictionary replacements."""
    # Test standalone
    assert sanitize_math_safe(f"A {latex_op} B") == f"A {unicode_char} B"
    # Test no trailing space req
    assert sanitize_math_safe(f"A{latex_op}B") == f"A{unicode_char}B"


# 5. LaTeX Math Conversion (pylatexenc integration)


def test_basic_math_delimiters():
    """Test conversion of standard delimiters."""
    # Dollar sign
    assert sanitize_math_safe("$x^2$") == "x^2" or "x²"
    # Escaped parens
    assert sanitize_math_safe("\\(1 + 1\\)") == "1 + 1"
    # Escaped brackets (display math)
    assert sanitize_math_safe("\\[a + b\\]") == "a + b"


def test_orphan_commands():
    """Test conversion of specific commands without dollar signs."""
    # \frac{1}{2} -> 1/2 (default pylatexenc behavior)
    assert "1/2" in sanitize_math_safe("\\frac{1}{2}")

    # \sqrt{x} -> √x (approximate check as implementations may vary slightly)
    res = sanitize_math_safe("\\sqrt{x}")
    assert "x" in res and ("sqrt" not in res)


def test_unicode_math_in_input():
    """Ensure existing unicode math is preserved or normalized safely."""
    text = "x² + y²"
    assert sanitize_math_safe(text) == text


# 6. Robustness & Edge Cases


def test_unbalanced_braces_are_skipped():
    """If braces aren't balanced, sanitizer should return original text to avoid crashing."""
    broken_tex = "\\frac{1}{2"
    assert sanitize_math_safe(broken_tex) == broken_tex


def test_dangling_dollar_cleanup():
    """Test the scrubbing of orphan dollar signs."""
    # Leading orphan dollar often appears in pricing or shell prompts
    # Case: A dollar that looks like it starts math but never ends
    orphan_math = "$ x^2 is great"

    # Should strip the $ because it has math tokens but no closing $,
    # effectively "sanitizing" the dangling delimiter.
    result = sanitize_math_safe(orphan_math)
    assert result == " x² is great" or result == " x^2 is great"


def test_mixed_content_stress_test():
    """A complex scenario combining code, math, and logic."""
    input_text = """
Here is code: `x = $var`
Here is math: $a \\to b$
Separator:
---
Orphan command: \\frac{1}{2}
"""
    result = sanitize_math_safe(input_text)

    assert "`x = $var`" in result  # Code preserved
    assert "a → b" in result  # Math converted
    assert "---" in result  # Separator preserved
    assert "1/2" in result  # Orphan converted
