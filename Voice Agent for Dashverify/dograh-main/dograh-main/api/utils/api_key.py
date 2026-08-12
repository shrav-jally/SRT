import hashlib
import secrets
from typing import Tuple


def generate_api_key() -> Tuple[str, str, str]:
    """Generate a new API key with its hash and prefix.

    Returns:
        Tuple of (raw_api_key, key_hash, key_prefix)
        - raw_api_key: The actual API key to give to the user
        - key_hash: SHA256 hash of the key for storage
        - key_prefix: First 8 characters for display purposes
    """
    raw_api_key = f"dgr_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
    key_prefix = raw_api_key[:8]

    return raw_api_key, key_hash, key_prefix


def hash_api_key(raw_api_key: str) -> str:
    """Hash an API key for comparison.

    Args:
        raw_api_key: The raw API key to hash

    Returns:
        SHA256 hash of the API key
    """
    return hashlib.sha256(raw_api_key.encode()).hexdigest()
