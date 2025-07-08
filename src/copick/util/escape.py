import re
import warnings


def sanitize_name(input_str: str, suppress_warnings=False) -> str:
    """
    Replace invalid characters in a string that is intended for use as a copick object name, user_id or session_id.
    Raises ValueError if the input is invalid, and issues a warning if the input is modified.

    Args:
        input_str: The input string.
        suppress_warnings: If True, suppress warnings about sanitization. Defaults to False.

    Returns:
        str: The sanitized input.
    """
    # Define a regex pattern for invalid characters
    # Invalid characters: <>:"/\|?* (Windows), control chars, spaces, and underscores
    invalid_chars = r'[<>:"/\\|?*\x00-\x1F\x7F\s_]'

    # Replace invalid characters with dashes
    sanitized = re.sub(invalid_chars, "-", input_str)

    # Ensure the filename is not empty or just dashes
    sanitized = sanitized.strip("-")

    if sanitized == "":
        raise ValueError("Filename cannot be empty or completely consist of invalid characters.")

    if sanitized != input_str and not suppress_warnings:
        warnings.warn(
            f"Input '{input_str}' contains invalid characters. It has been sanitized to '{sanitized}'.",
            UserWarning,
            stacklevel=2,
        )

    return sanitized
