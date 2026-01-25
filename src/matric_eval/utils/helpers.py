"""Helper utility functions."""


def sanitize_model_name(model_name: str) -> str:
    """
    Sanitize model name for use in filesystem paths.

    Args:
        model_name: Original model name (e.g., "llama3.2:3b")

    Returns:
        Sanitized name safe for filesystem (e.g., "llama3.2_3b")

    Examples:
        >>> sanitize_model_name("llama3.2:3b")
        'llama3.2_3b'
        >>> sanitize_model_name("codestral/22b")
        'codestral_22b'
    """
    return model_name.replace(":", "_").replace("/", "_")
