"""
Cryptographic utilities for BLE symmetric key authentication.

Provides AES-128-CBC encryption/decryption and HKDF-SHA256 key derivation.
"""

import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# Constants
KEY_SIZE = 16  # 128 bits
IV_SIZE = 16   # AES block size
NONCE_SIZE = 16


def generate_random_bytes(size: int) -> bytes:
    """Generate cryptographically secure random bytes."""
    return os.urandom(size)


def generate_nonce() -> bytes:
    """Generate a random 16-byte nonce."""
    return generate_random_bytes(NONCE_SIZE)


def generate_iv() -> bytes:
    """Generate a random 16-byte IV for AES-CBC."""
    return generate_random_bytes(IV_SIZE)


def derive_device_key(master_key: bytes, device_id: bytes) -> bytes:
    """
    Derive a device-specific key from the master key and device ID using HKDF-SHA256.

    Args:
        master_key: The 16-byte master key
        device_id: The 16-byte device identifier

    Returns:
        16-byte derived device key
    """
    if len(master_key) != KEY_SIZE:
        raise ValueError(f"Master key must be {KEY_SIZE} bytes")
    if len(device_id) != KEY_SIZE:
        raise ValueError(f"Device ID must be {KEY_SIZE} bytes")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=device_id,
        info=b"device-key",
        backend=default_backend()
    )
    return hkdf.derive(master_key)


def pad_data(data: bytes) -> bytes:
    """Apply PKCS7 padding to data for AES block size."""
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    return padder.update(data) + padder.finalize()


def unpad_data(data: bytes) -> bytes:
    """Remove PKCS7 padding from data."""
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    return unpadder.update(data) + unpadder.finalize()


def encrypt(key: bytes, plaintext: bytes, iv: bytes = None) -> tuple[bytes, bytes]:
    """
    Encrypt data using AES-128-CBC.

    Args:
        key: 16-byte encryption key
        plaintext: Data to encrypt
        iv: Optional 16-byte IV (generated if not provided)

    Returns:
        Tuple of (iv, ciphertext)
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"Key must be {KEY_SIZE} bytes")

    if iv is None:
        iv = generate_iv()
    elif len(iv) != IV_SIZE:
        raise ValueError(f"IV must be {IV_SIZE} bytes")

    # Pad the plaintext
    padded_data = pad_data(plaintext)

    # Encrypt
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    return iv, ciphertext


def decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    """
    Decrypt data using AES-128-CBC.

    Args:
        key: 16-byte decryption key
        iv: 16-byte IV used during encryption
        ciphertext: Encrypted data

    Returns:
        Decrypted plaintext

    Raises:
        ValueError: If decryption or padding removal fails
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"Key must be {KEY_SIZE} bytes")
    if len(iv) != IV_SIZE:
        raise ValueError(f"IV must be {IV_SIZE} bytes")
    if len(ciphertext) == 0 or len(ciphertext) % IV_SIZE != 0:
        raise ValueError("Ciphertext length must be a multiple of block size")

    # Decrypt
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove padding
    return unpad_data(padded_plaintext)
