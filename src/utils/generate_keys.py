#!/usr/bin/env python3
"""Generate Ed25519 key pair for BLE challenge-response demo.

Usage:
    uv run python utils/generate_keys.py

This generates a matching public/private key pair that can be used for
the challenge-response authentication flow between client and server.
This file was run standalone to generate and copy/paste the keys for demo purposes.
Absolutely was not meant to be used in production code. if it is, talk with someone :) 
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    PublicFormat,
    NoEncryption,
)


def generate_keypair():
    """Generate and display an Ed25519 key pair."""
    # Generate a new Ed25519 key pair
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Serialize to PEM format
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    public_pem = public_key.public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )

    print("=" * 70)
    print("CLIENT PRIVATE KEY - Add to: src/ble_client/client.py")
    print("=" * 70)
    print(f'CLIENT_PRIVATE_KEY_PEM = b"""{private_pem.decode()}"""')
    print()

    print("=" * 70)
    print("CLIENT PUBLIC KEY - Add to: src/ble_door_unlock_server/server.py")
    print("=" * 70)
    print(f'CLIENT_PUBLIC_KEY_PEM = b"""{public_pem.decode()}"""')
    print()

    # Test signing/verification to ensure keys work
    test_nonce = b"0123456789abcdef"
    signature = private_key.sign(test_nonce)
    public_key.verify(signature, test_nonce)
    print("=" * 70)
    print("Key pair verified successfully!")
    print("The private key can sign data that the public key can verify.")
    print("=" * 70)


if __name__ == "__main__":
    generate_keypair()
