#!/usr/bin/env python3
"""Initialize the database tables.

Run this script to create all database tables.
Usage: python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Base, init_db, get_engine


async def main():
    """Initialize database tables."""
    print("Initializing ZURK database...")

    try:
        await init_db()

        # Print created tables
        engine = get_engine()
        print(f"Database URL: {engine.url}")
        print("\nCreated tables:")
        for table in Base.metadata.tables:
            print(f"  - {table}")

        print("\nDatabase initialization complete!")

    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
