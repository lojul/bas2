"""Check OneDrive folder structure."""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from src.nodes.onedrive import list_onedrive_files, get_access_token


def main():
    drive_id = os.environ.get("MS_GRAPH_DRIVE_ID")
    print(f"Drive ID: {drive_id[:20]}..." if drive_id else "No DRIVE_ID set!")
    print()

    # Test authentication
    print("Testing authentication...")
    try:
        token = get_access_token()
        print(f"✓ Got access token: {token[:20]}...")
    except Exception as e:
        print(f"✗ Auth failed: {e}")
        return

    print()

    # List root folder
    print("=== Root folder ===")
    try:
        files = list_onedrive_files(drive_id, "/")
        if not files:
            print("(empty or no files)")
        for f in files:
            print(f"  - {f['name']} (id: {f['id'][:15]}...)")
    except Exception as e:
        print(f"Error: {e}")

    print()

    # Check Document Processor folder
    print("=== /Document Processor ===")
    try:
        files = list_onedrive_files(drive_id, "/Document Processor")
        if not files:
            print("(empty or only subfolders)")
        for f in files:
            print(f"  - {f['name']} (id: {f['id'][:15]}...)")
    except Exception as e:
        print(f"Error or folder not found: {e}")

    print()

    # Check In folder
    print("=== /Document Processor/In ===")
    try:
        files = list_onedrive_files(drive_id, "/Document Processor/In")
        if not files:
            print("(empty)")
        for f in files:
            print(f"  - {f['name']} (id: {f['id'][:15]}...)")
    except Exception as e:
        print(f"Error or folder not found: {e}")

    print()

    # Check Processed folder
    print("=== /Document Processor/Processed ===")
    try:
        files = list_onedrive_files(drive_id, "/Document Processor/Processed")
        if not files:
            print("(empty)")
        for f in files:
            print(f"  - {f['name']} (id: {f['id'][:15]}...)")
    except Exception as e:
        print(f"Error or folder not found: {e}")


if __name__ == "__main__":
    main()
