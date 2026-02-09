#!/usr/bin/env python3
"""Verify claude-agent-sdk installation and basic functionality.

This script tests that we can:
1. Import the SDK
2. Access key functions and classes
3. (With API key) Run a minimal query and capture session ID
"""

import os
import sys


def main():
    print("=" * 60)
    print("Claude Agent SDK Verification")
    print("=" * 60)

    # Test 1: Import the SDK
    print("\n1. Testing SDK import...")
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
        print("   ✓ Successfully imported 'query' function")
        print("   ✓ Successfully imported 'ClaudeAgentOptions' class")
    except ImportError as e:
        print(f"   ✗ Failed to import SDK: {e}")
        sys.exit(1)

    # Test 2: Check for API key
    print("\n2. Checking for ANTHROPIC_API_KEY...")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Try loading from .env
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        except ImportError:
            pass

    if api_key and api_key.startswith("sk-ant-"):
        print("   ✓ API key found (starts with sk-ant-)")
    else:
        print("   ⚠ No valid API key found")
        print("   → Set ANTHROPIC_API_KEY in .env to run live tests")
        print("\n" + "=" * 60)
        print("SDK import verification: PASSED")
        print("Live query test: SKIPPED (no API key)")
        print("=" * 60)
        return

    # Test 3: Run a minimal query
    print("\n3. Running minimal SDK query...")
    import asyncio

    async def test_query():
        """Run a simple test query and capture the session ID."""
        session_id = None
        response_received = False

        try:
            # Create a simple query - just ask for a brief response
            async for message in query(
                prompt="Respond with only the word 'hello'",
                options=ClaudeAgentOptions(
                    max_turns=1,
                    allowed_tools=[],  # No tools needed for this test
                ),
            ):
                # Debug: show message type
                msg_type = getattr(message, "type", "unknown")
                subtype = getattr(message, "subtype", None)

                if msg_type == "system" and subtype == "init":
                    # Capture session ID from init message
                    session_id = getattr(message, "session_id", None)
                    print(f"   ✓ Session started (ID: {session_id[:20]}...)")

                elif msg_type == "assistant":
                    # Got a response
                    content = getattr(message, "content", [])
                    if content:
                        text = content[0].text if hasattr(content[0], "text") else str(content[0])
                        print(f"   ✓ Response received: {text[:50]}")
                        response_received = True

                elif msg_type == "result":
                    # Query completed
                    cost = getattr(message, "total_cost_usd", 0)
                    print(f"   ✓ Query completed (cost: ${cost:.4f})")

        except Exception as e:
            print(f"   ✗ Query failed: {e}")
            return None, False

        return session_id, response_received

    session_id, response_ok = asyncio.run(test_query())

    # Summary
    print("\n" + "=" * 60)
    if session_id and response_ok:
        print("SDK Verification: PASSED")
        print(f"  - Session ID capture: ✓")
        print(f"  - Message streaming: ✓")
        print(f"  - Response generation: ✓")
    else:
        print("SDK Verification: PARTIAL")
        print(f"  - Session ID capture: {'✓' if session_id else '✗'}")
        print(f"  - Response generation: {'✓' if response_ok else '✗'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
