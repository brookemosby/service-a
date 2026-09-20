"""Canonical env/stack identifier derived from a git branch name."""

DEFAULT_ENV_ID = "preview"
_EXTRA_ALLOWED = "._-"


def _is_safe_env_char(ch):
    return ch.isalnum() or ch in _EXTRA_ALLOWED


def normalize_env_id(branch):
    """Lowercase branch name and replace characters unsafe in CFN/URL paths."""
    normalized = "".join(
        ch if _is_safe_env_char(ch) else "-" for ch in branch.strip().lower()
    )
    normalized = normalized.strip("-")
    return normalized or DEFAULT_ENV_ID
