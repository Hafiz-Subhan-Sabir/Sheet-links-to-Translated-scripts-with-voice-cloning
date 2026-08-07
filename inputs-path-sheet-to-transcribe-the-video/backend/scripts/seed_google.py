"""Verify Google OAuth tokens and Sheet append (requires configured .env)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def main():
    from app.services.auth import get_credentials, get_user_email
    from app.services.storage import storage

    creds = get_credentials()
    if not creds:
        print("ERROR: No Google tokens found. Connect via /api/auth/google first.")
        sys.exit(1)

    email = get_user_email()
    print(f"Connected as: {email}")

    cfg = storage.get_admin_config()
    sheet_url = cfg.get("sheet_url")
    if not sheet_url:
        print("ERROR: Admin sheet URL not configured.")
        sys.exit(1)

    from app.services.google_integrations import append_to_sheet

    append_to_sheet(
        sheet_url=sheet_url,
        title="Seed Test Entry",
        doc_url="https://docs.google.com/document/d/test",
        date="2026-06-20",
        time="12:00",
        source_video="seed-script",
        language="en",
    )
    print("SUCCESS: Row appended to registry sheet.")


if __name__ == "__main__":
    main()
