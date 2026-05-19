#!/usr/bin/env python3
"""Test script for the agent."""

import os
from dotenv import load_dotenv

# Load .env file if exists
load_dotenv()

# Set MINIMAX_API_KEY if provided inline (for testing only)
# In production, set it via environment variable before running

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
if not MINIMAX_API_KEY:
    print("Error: MINIMAX_API_KEY not set")
    print("Run: export MINIMAX_API_KEY=your_key && python test_agent.py")
    exit(1)

# Test imports
print("Testing imports...")
from providers.factory import ProviderFactory
from core.session import Session
from core.agent_loop import AgentLoop
from tools.base import get_tools_schema, execute_tool
from tools.file_ops import read_file, write_file
from tools.dir_ops import list_dir, change_dir, stat_path

print("[OK] All imports successful")

# Test provider creation
print("\nTesting provider creation...")
try:
    provider = ProviderFactory.create_from_config()
    print(f"[OK] Provider created: {provider.get_name()}")
except Exception as e:
    print(f"[ERROR] Provider error: {e}")
    exit(1)

# Test tools schema
print("\nTesting tools schema...")
schemas = get_tools_schema()
print(f"[OK] {len(schemas)} tools registered:")
for s in schemas:
    print(f"  - {s['function']['name']}: {s['function']['description']}")

# Test session
print("\nTesting session...")
session = Session.new(os.getcwd())
print(f"[OK] Session created: {session.session_id[:8]}...")
session.add_message("user", "test message")
print(f"[OK] Message added, total: {len(session.messages)}")

print("\n" + "="*50)
print("All tests passed! Run 'python agent.py' to start the REPL.")
print("="*50)
