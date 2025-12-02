"""
Utility functions for Mail2RAG application.
Provides common helpers for string manipulation and logging.
"""

import re
from email.header import decode_header, make_header
from typing import Any, Optional

# Pré-compilé pour éviter de recréer la regex à chaque appel.
_WHITESPACE_RE = re.compile(r"\s+")


def decode_email_header(header_value: Any) -> str:
    """
    Decode email header value handling various encodings.

    Args:
        header_value: Raw email header value (string or None or header object)

    Returns:
        str: Decoded header string, or empty string if None/empty.
    """
    if not header_value:
        return ""
    return str(make_header(decode_header(header_value)))


def sanitize_filename(text: Optional[str], max_length: int = 100) -> str:
    """
    Sanitize text to create a safe filename.

    Args:
        text: Input text to sanitize (can be None)
        max_length: Maximum length of result (default: 100)

    Returns:
        str: Sanitized filename with only alphanumeric, dot, underscore, dash.
             Whitespace is collapsed and replaced by underscores.
    """
    if not text:
        return ""

    # Garder seulement alphanumériques + espace + . _ -
    safe = "".join(
        c for c in text
        if c.isalnum() or c in (" ", ".", "_", "-")
    ).strip()

    # Remplacer les séquences d'espaces par un underscore
    safe = _WHITESPACE_RE.sub("_", safe)

    return safe[:max_length]


def truncate_log(
    content: Any,
    head: int = 5,
    tail: int = 3,
    max_line_length: int = 500,
) -> str:
    """
    Truncate log content for readability.
    Keeps first N and last M lines, truncates long lines.

    Args:
        content: Log content to truncate (any type, converted to str)
        head: Number of lines to keep at start (default: 5)
        tail: Number of lines to keep at end (default: 3)
        max_line_length: Maximum length per line (default: 500)

    Returns:
        str: Truncated log content
    """
    if not isinstance(content, str):
        content = str(content)

    lines = content.splitlines()
    truncated_lines = []

    for line in lines:
        if len(line) > max_line_length:
            truncated_lines.append(
                line[:max_line_length] + " ... [TRONQUÉ] ..."
            )
        else:
            truncated_lines.append(line)

    lines = truncated_lines

    # Rien ou peu de lignes : on renvoie tel quel
    if len(lines) <= head + tail + 1:
        return "\n".join(lines)

    hidden_count = len(lines) - (head + tail)

    return (
        "\n".join(lines[:head])
        + f"\n... [{hidden_count} LIGNES MASQUÉES] ...\n"
        + "\n".join(lines[-tail:])
    )
