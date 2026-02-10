"""
Shared test fixtures for the HOUSE EDGE test suite.
"""

import sys
import os
from pathlib import Path

# Ensure project root is on sys.path so engine.* imports resolve
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Disable any network calls during tests by default
os.environ.setdefault("ODDS_API_KEY", "test-key-not-real")
os.environ.setdefault("HOUSE_EDGE_API_KEY", "test-api-key")
