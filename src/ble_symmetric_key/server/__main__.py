"""
Entry point for running the GATT server as a module.

Usage:
    python -m ble_symmetric_key.server
    python -m ble_symmetric_key.server --master-key 00112233445566778899aabbccddeeff
"""

import asyncio
from .server import main

if __name__ == "__main__":
    asyncio.run(main())
