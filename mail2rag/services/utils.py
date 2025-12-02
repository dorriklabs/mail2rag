"""
Utility functions for Mail2RAG application.
Provides common helpers for string manipulation and logging.
"""

import re
from email.header import decode_header, make_header


def decode_email_header(header_value):
    """
    Decode email header value handling various encodings.
    
    Args:
        header_value: Raw email header value
        
    Returns:
        str: Decoded header string, or empty string if None
    """
    if not header_value:
        return ""
    return str(make_header(decode_header(header_value)))


def sanitize_filename(text, max_length=100):
    """
    Sanitize text to create a safe filename.
    
    Args:
        text: Input text to sanitize
        max_length: Maximum length of result (default: 100)
        
    Returns:
        str: Sanitized filename with only alphanumeric, dot, underscore, dash
    """
    safe = "".join([c for c in text if c.isalnum() or c in (' ', '.', '_', '-')]).strip()
    safe = re.sub(r'\s+', '_', safe)
    return safe[:max_length]


def truncate_log(content, head=5, tail=3, max_line_length=500):
    """
    Truncate log content for readability.
    Keeps first N and last M lines, truncates long lines.
    
    Args:
        content: Log content to truncate
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
            truncated_lines.append(line[:max_line_length] + " ... [TRONQUÉ] ...")
        else:
            truncated_lines.append(line)
    
    lines = truncated_lines
    
    if len(lines) <= (head + tail + 1):
        return "\n".join(lines)
    
    return (
        "\n".join(lines[:head]) + 
        f"\n... [{len(lines) - (head + tail)} LIGNES MASQUÉES] ...\n" + 
        "\n".join(lines[-tail:])
    )
