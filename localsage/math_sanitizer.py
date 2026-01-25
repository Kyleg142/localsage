"""
LaTeX-to-Unicode/ASCII math sanitizer for live Markdown.

- Detects and converts LaTeX formatted math while preserving Markdown formatting.
- Skips fenced code and inline code spans.
- Skips incomplete LaTeX mid-stream (no pylatexenc warnings)

REMINDER: The math sanitizer can only work properly on valid formatting!
- If an LLM hallucinates or butchers it's LaTeX or Markdown formatting,
  that is not a bug with the sanitizer.
- Dangling '$' delimiters are scrubbed, that is as far as this project will
  go in regards to correcting output that is broken from the source.
"""

# Some shell globals within big code blocks are the only 'collateral' that
# triggers a false-positive. These false-positives are restored after
# the code block is exited by the ``` delimiter.

from __future__ import annotations

import html
import logging
import re

from pylatexenc.latex2text import LatexNodes2Text, get_default_latex_context_db

# ────────────────────────────────────────────────────────────────────────────────
# Normalization prefilter: cleans model output quirks before Markdown parsing.

# Common Unicode glyphs and pretty replacements occasionally emitted by models
_UNICODE_FIXES = str.maketrans(
    {
        "＃": "#",  # fullwidth hash
        "＊": "*",  # fullwidth asterisk
        "﹍": "_",  # low line variants
        "﹎": "_",
        "‐": "-",  # hyphen
        "–": "-",  # en dash
        "—": "-",  # em dash
        "―": "-",  # horizontal bar
        "…": "...",  # ellipsis
        "·": "*",  # middle dot used for bullets
        "•": "*",
        "∗": "*",  # mathematical asterisk
    }
)


def _normalize_pre(text: str) -> str:
    """
    Normalize model output quirks before Markdown/LaTeX sanitization.
    - Converts Unicode homoglyphs to ASCII equivalents.
    - Unescapes HTML entities (&lt;, &gt;, &amp;, etc.).
    - Replaces smart quotes/apostrophes with plain ASCII equivalents.
    """
    if not text:
        return text

    # Normalize certain Unicode variants to ASCII for consistency
    text = text.translate(_UNICODE_FIXES)

    # Decode HTML entities (e.g., &lt; to <)
    if "&" in text:
        text = html.unescape(text)

    # Replace smart quotes and apostrophes with straight ASCII versions
    text = text.translate(
        {
            ord("“"): '"',
            ord("”"): '"',
            ord("„"): '"',
            ord("‟"): '"',
            ord("‘"): "'",
            ord("’"): "'",
            ord("‚"): "'",
            ord("‛"): "'",
        }
    )

    # Space normalization, disabled for visual fidelity, made math look odd
    # text = text.replace("\u00A0", " ")   # NBSP
    # text = text.replace("\u202F", " ")   # narrow NBSP
    # text = text.replace("\u2009", " ")   # thin space

    # Remove zero-width spaces and direction marks. Future-proofs the stream against invisible corruption.
    # I haven't noticed any difference in testing.
    text = re.sub(r"[\u200B-\u200F\u202A-\u202E\u2060]", "", text)

    return text


# ────────────────────────────────────────────────────────────────────────────────

# Setup for pylatexenc
logging.getLogger("pylatexenc").setLevel(logging.ERROR)
ctx = get_default_latex_context_db()
_L2T = LatexNodes2Text(math_mode="text", latex_context=ctx).latex_to_text

# LaTeX math delims
_MATH_DELIMS = (
    re.compile(r"\$(.+?)\$", re.DOTALL),
    re.compile(r"\\\((.+?)\\\)", re.DOTALL),
    re.compile(r"\\\[(.+?)\\\]", re.DOTALL),
)

# Orphan LaTeX commands like \log_b, \frac{...}{...}, \sqrt{x}, etc.
# Old regex: \\[A-Za-z]+(?:_[A-Za-z0-9]+)?(?:\{[^{}]*\})*(?:\{[^{}]*\})*
_ORPHAN = re.compile(
    r"\\[A-Za-z]+(?![a-zA-Z])(?:_[A-Za-z0-9]+(?![A-Za-z0-9]))?(?:\{[^{}]*\})*(?!\{)"
)

# Orphan dollar cleanup
# Old regex: (?m)(?<![`$])\$(?=(?:[^$\n])*?(?:[\^_\\]))(?=(?:[^$\n])*$)
_ORPHAN_DOLLAR_LEADING = re.compile(r"(?m)(?<![`$])\$(?=(?:[^$\n]*[\^_\\])[^$\n]*$)")
# Old regex: (?m)(?<!\$)\$\s*$
_ORPHAN_DOLLAR_TRAILING = re.compile(r"(?m)(?<!\$)\$(?=\s*$)")

# Fenced code blocks (```…```) or inline code (`…`)
_CODE_BLOCKS = re.compile(r"(```.*?```|`[^`]+`)", re.DOTALL)

# Placeholder restore for codeblocks
_CODEPH_RE = re.compile(r"\{CODEBLOCK_(\d+)\}")

_CODEPH_ANY_RE = re.compile(r"(?:\{CODEBLOCK_(\d+)\}|CODEBLOCK_(\d+))")

# Logic operators to Unicode (handled outside code, before LaTeX conversion)
_LOGIC_OPS = {
    "iff": "⇔",
    "implies": "⇒",
    "Longrightarrow": "⇒",
    "to": "→",
    "rightarrow": "→",
    "Rightarrow": "⇒",
    "gets": "←",
    "leftarrow": "←",
    "Leftarrow": "⇐",
    "Leftrightarrow": "⇔",
    "Longleftrightarrow": "⇔",
    "mapsto": "↦",
    "because": "∵",
    "therefore": "∴",
}
# Old regex:  \\(?:iff|implies|Longrightarrow|to|rightarrow|Rightarrow|gets|leftarrow|Leftarrow|Leftrightarrow|Longleftrightarrow|mapsto|because|therefore)\b
_RE_LOGIC_OPS = re.compile(
    r"\\(?:iff|implies|Longrightarrow|to|rightarrow|Rightarrow|gets|leftarrow|Leftarrow|Leftrightarrow|Longleftrightarrow|mapsto|because|therefore)(?![a-z])"
)


def _convert_safe(fragment: str) -> str:
    # Runner for pylatexenc
    try:
        return _L2T(fragment)
    except Exception:
        return fragment


def _balanced(fragment: str) -> bool:
    # Braces only. Cheap, streaming safe
    return fragment.count("{") == fragment.count("}")


# Robust placeholder markers for Markdown separators
_MDSEP_TOKEN_FMT = "⟦MDSEP_{i}⟧"
_MDSEP_ANY_RE = re.compile(r"(?:\{MDSEP_(\d+)\}|⟦MDSEP_(\d+)⟧|MDSEP_(\d+))")

# Lines that are horizontal rules: --- *** ___ (with optional surrounding spaces)
_SEPARATOR_RE = re.compile(r"^(?:\s*)([-*_])\1\1(?:\s*)$", re.MULTILINE)


def _preserve_md_separators(text: str) -> tuple[str, list[str]]:
    """Protect Markdown separators (---, ***, ___) from LaTeX parsing/normalization."""
    seps: list[str] = []

    def _sep_repl(m: re.Match[str]) -> str:
        seps.append(m.group(0))
        return _MDSEP_TOKEN_FMT.format(i=len(seps) - 1)

    return _SEPARATOR_RE.sub(_sep_repl, text), seps


def _restore_md_separators(text: str, seps: list[str]) -> str:
    """Restore separators even if placeholder lost braces or different wrapper."""
    if not seps:
        return text

    def _restore(m: re.Match[str]) -> str:
        # Figure out which capturing group matched (1, 2, or 3)
        for g in (1, 2, 3):
            if m.group(g) is not None:
                idx = int(m.group(g))
                return seps[idx] if 0 <= idx < len(seps) else m.group(0)
        return m.group(0)

    return _MDSEP_ANY_RE.sub(_restore, text)


def sanitize_math_safe(text: str) -> str:
    """
    Convert LaTeX math fragments to readable text while preserving Markdown.
    Streaming-safe: skips incomplete math and never raises.
    """

    # Normalize model output before processing
    text = _normalize_pre(text)

    # Fast path: nothing to do
    if ("\\" not in text) and ("$" not in text):
        return text

    # 0) Preserve Markdown separators *before* any LaTeX-related work
    text, seps = _preserve_md_separators(text)

    # 1) Extract and protect code spans
    code_spans: list[str] = []

    def _code_preserve(m: re.Match[str]) -> str:
        code = m.group(0)
        code_spans.append(code)
        return f"{{CODEBLOCK_{len(code_spans) - 1}}}"

    text = _CODE_BLOCKS.sub(_code_preserve, text)

    # 1.5) Logic operators outside code
    if "\\" in text:

        def _logic_repl(m: re.Match[str]) -> str:
            name = m.group(0)[1:]  # drop backslash
            return _LOGIC_OPS.get(name, m.group(0))

        text = _RE_LOGIC_OPS.sub(_logic_repl, text)

    # 2) Convert math outside code but skip if an MDSEP token is inside the match
    if "$" in text or "\\" in text:
        for pat in _MATH_DELIMS:
            text = pat.sub(
                lambda m: (
                    m.group(0)  # leave as-is if placeholder present
                    if "MDSEP_" in m.group(1)
                    else (
                        _convert_safe(m.group(1))
                        if _balanced(m.group(1))
                        else m.group(0)
                    )
                ),
                text,
            )

        text = _ORPHAN.sub(
            lambda m: _convert_safe(m.group(0))
            if _balanced(m.group(0))
            else m.group(0),
            text,
        )

    # 2.5) Clean up true dangling math '$' and never touch shell/currency
    # Leading orphan '$' on a line that clearly starts math and has no closer
    text = _ORPHAN_DOLLAR_LEADING.sub("", text)
    # Trailing orphan '$' at end of line (rare but can happen)
    text = _ORPHAN_DOLLAR_TRAILING.sub("", text)

    # 3) Restore protected code spans
    if code_spans:

        def _restore_codeph(m: re.Match[str]) -> str:
            for g in (1, 2):
                if m.group(g) is not None:
                    idx = int(m.group(g))
                    return code_spans[idx] if 0 <= idx < len(code_spans) else m.group(0)
            return m.group(0)

        text = _CODEPH_ANY_RE.sub(_restore_codeph, text)

    # 4) Restore Markdown separators (handles {MDSEP_n}, ⟦MDSEP_n⟧, or bare MDSEP_n)
    text = _restore_md_separators(text, seps)

    return text
