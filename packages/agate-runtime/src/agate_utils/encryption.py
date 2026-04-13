"""Encryption utilities for API keys using Fernet symmetric encryption."""

import os
import base64
from cryptography.fernet import Fernet
from typing import Optional


def _get_master_key() -> str:
    """Get the master encryption key from environment variables."""
    master_key = os.getenv("MASTER_ENCRYPTION_KEY")
    if not master_key:
        raise ValueError(
            "MASTER_ENCRYPTION_KEY environment variable not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return master_key


def encrypt_api_key(value: str, master_key: Optional[str] = None) -> str:
    """
    Encrypt an API key using Fernet symmetric encryption.
    
    Args:
        value: The API key value to encrypt
        master_key: Optional master key, will use env var if not provided
        
    Returns:
        Base64-encoded encrypted string
        
    Raises:
        ValueError: If master key is not available
    """
    if master_key is None:
        master_key = _get_master_key()
    
    if not value:
        raise ValueError("API key value cannot be empty")
    
    # Create Fernet instance with the master key
    # Fernet expects the key to be base64-encoded bytes
    fernet = Fernet(master_key.encode())
    
    # Encrypt the value
    encrypted_bytes = fernet.encrypt(value.encode())
    
    # Return as base64 string for storage
    return base64.b64encode(encrypted_bytes).decode()


def decrypt_api_key(encrypted_value: str, master_key: Optional[str] = None) -> str:
    """
    Decrypt an API key using Fernet symmetric encryption.
    
    Args:
        encrypted_value: Base64-encoded encrypted string
        master_key: Optional master key, will use env var if not provided
        
    Returns:
        Decrypted API key string
        
    Raises:
        ValueError: If master key is not available or decryption fails
    """
    if master_key is None:
        master_key = _get_master_key()
    
    if not encrypted_value:
        raise ValueError("Encrypted value cannot be empty")
    
    try:
        # Create Fernet instance with the master key
        # Fernet expects the key to be base64-encoded bytes
        fernet = Fernet(master_key.encode())
        
        # Decode from base64
        encrypted_bytes = base64.b64decode(encrypted_value.encode())
        
        # Decrypt the value
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        
        # Return as string
        return decrypted_bytes.decode()
        
    except Exception as e:
        raise ValueError(f"Failed to decrypt API key: {str(e)}")


def generate_master_key() -> str:
    """
    Generate a new master encryption key.
    
    Returns:
        Base64-encoded encryption key suitable for MASTER_ENCRYPTION_KEY env var
    """
    return Fernet.generate_key().decode()
