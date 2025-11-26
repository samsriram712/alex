"""
Tools for the Alex Researcher agent
"""
import os
import json
from typing import Dict, Any
from datetime import datetime, UTC
from agents import function_tool
# from src import Database
from database.src.models import get_latest_price

@function_tool
async def get_latest_price_tool(symbols: list[str]) -> str:
    """
    Retrieve latest stock prices for given symbols.
    """
    try:
        results = get_latest_price(symbols)
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error retrieving latest prices: {e}"