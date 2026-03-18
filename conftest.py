"""
Pytest conftest — sets TESTING before app imports.
"""
import os

# Set testing env BEFORE any app imports
os.environ["TESTING"] = "1"
