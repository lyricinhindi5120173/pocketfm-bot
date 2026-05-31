import os
import requests

TOKEN = os.getenv("POCKETFM_ACCESS_TOKEN", "")

def get_session_status():
    if not TOKEN:
        return False, "POCKETFM_ACCESS_TOKEN missing in Render environment."

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Cookie": f"auth-token={TOKEN}; locale=IN; language=hindi",
    }

    r = requests.get(
        "https://pocketfm.com/api/auth/session",
        headers=headers,
        timeout=20,
    )

    return r.status_code == 200, r.text[:500]
