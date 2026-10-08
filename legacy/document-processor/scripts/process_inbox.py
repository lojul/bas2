"""Process files from OneDrive /In folder.

This script orchestrates the folder-level workflow:
1. List files in /In folder
2. For each file, run through the LangGraph workflow
3. (Optional) Move to /Processed when done
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from langsmith import traceable

from src.graph import process_file  # Uses the graph!
from src.nodes.onedrive import list_onedrive_files, move_to_processed
from src.state import ProcessingStatus
from src.store import ProcessedFile, save_result


@traceable(name="process_inbox", run_type="chain")
def process_inbox(move_when_done: bool = False):
    """Process all files in the /In folder.

    Args:
        move_when_done: If True, move files to /Processed after OCR
    """
    drive_id = os.environ.get("MS_GRAPH_DRIVE_ID")

    # Step 1: List files in /In folder
    print("Checking /Document Processor/In...")
    files = list_onedrive_files(
        drive_id,
        "/Document Processor/In",
        file_extensions=[".pdf", ".jpg", ".jpeg", ".png"]
    )

    if not files:
        print("No files found in /In folder")
        return

    print(f"Found {len(files)} file(s) to process")
    print()

    # Get Processed folder ID if needed
    processed_folder_id = None
    if move_when_done:
        import httpx
        from src.nodes.onedrive import get_access_token

        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        folder_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/Document Processor/Processed"

        with httpx.Client() as client:
            resp = client.get(folder_url, headers=headers)
            resp.raise_for_status()
            processed_folder_id = resp.json()["id"]

    # Step 2: Process each file through the graph
    for file in files:
        file_id = file["id"]
        file_name = file["name"]

        print(f"Processing: {file_name}")

        # Run through LangGraph workflow
        result = process_file(file_id, file_name)

        # Show results
        if result.status == ProcessingStatus.ERROR:
            print(f"  ERROR: {result.error_message}")
            # Save error to dashboard
            save_result(ProcessedFile(
                file_name=file_name,
                status="error",
                document_type="unknown",
                text_preview="",
                text_length=0,
                tables_count=0,
                figures_count=0,
                processed_at=datetime.now().isoformat(),
                error_message=result.error_message,
            ))
            continue

        print(f"  OCR complete!")
        print(f"  - Text: {len(result.ocr.text or '')} characters")
        print(f"  - Tables: {len(result.ocr.tables or [])}")
        print(f"  - Figures: {len(result.ocr.figures or [])}")
        print(f"  - Type: {result.document_type.value} ({result.classification_confidence:.0%} confidence)")

        # Show extracted data
        if result.extracted and result.extracted.raw:
            import json
            print(f"  - Extracted data:")
            extracted_str = json.dumps(result.extracted.raw, indent=4, ensure_ascii=False)
            # Show first 500 chars of extracted data
            for line in extracted_str.split('\n')[:15]:
                print(f"      {line}")
            if len(extracted_str.split('\n')) > 15:
                print(f"      ...")

        # Preview text
        preview = ""
        if result.ocr.text:
            preview = result.ocr.text[:300].replace('\n', ' ')

        # Save to dashboard
        save_result(ProcessedFile(
            file_name=file_name,
            status="success",
            document_type=result.document_type.value if result.document_type else "unknown",
            text_preview=preview,
            text_length=len(result.ocr.text or ""),
            tables_count=len(result.ocr.tables or []),
            figures_count=len(result.ocr.figures or []),
            processed_at=datetime.now().isoformat(),
        ))

        # Step 3: Move to Processed (optional)
        if move_when_done and processed_folder_id:
            print("  Moving to /Processed...")
            move_to_processed(drive_id, file_id, processed_folder_id)

        print(f"  Done!")
        print()


if __name__ == "__main__":
    # Set move_when_done=True for production
    process_inbox(move_when_done=False)
