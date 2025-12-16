import os
import logging
from fastapi import Depends, HTTPException, Request
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer

from dotenv import load_dotenv
load_dotenv(override=True)

logger = logging.getLogger(__name__)

# Clerk authentication setup (exactly like saas reference)
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)

async def get_current_user_id(request: Request) -> str:
    """Extract user ID from validated Clerk token or return test user in DEV mode."""
    
    print("DEV_MODE =", os.getenv("DEV_MODE"))
    print("DEV_USER_ID =", os.getenv("DEV_USER_ID"))

    # ✅ LOG THE REAL AUTH HEADER
    auth_header = request.headers.get("authorization")
    logger.warning(f"Authorization header = {auth_header}")
    
    # --- DEV MODE ---
    if os.getenv("DEV_MODE") == "true":
        DEV_USER_ID = os.getenv("DEV_USER_ID", "test_user_001")
        return DEV_USER_ID

    # --- PROD MODE (Clerk required) ---
    clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
    clerk_guard = ClerkHTTPBearer(clerk_config)

    creds = await clerk_guard(request)
    if not creds or "sub" not in creds.decoded:
        raise HTTPException(status_code=403, detail="You don't have permission")

    user_id = creds.decoded["sub"]
    logger.info(f"Authenticated user: {user_id}")
    return user_id
