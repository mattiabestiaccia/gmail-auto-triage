"""One-shot script: remove AutoTriage/* labels from all emails, then delete the labels.

Usage: uv run python scripts/cleanup_labels.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from email_triage.auth import authenticate, get_gmail_service
from email_triage.labels import LABEL_PREFIX

CREDENTIALS = "credentials/credentials.json"
TOKEN = "credentials/token.json"


def main() -> None:
    creds = authenticate(CREDENTIALS, TOKEN)
    service = get_gmail_service(creds)

    # 1. Find all AutoTriage/* labels
    all_labels = service.users().labels().list(userId="me").execute().get("labels", [])
    triage_labels = [l for l in all_labels if l["name"].startswith(LABEL_PREFIX)]

    if not triage_labels:
        print("No AutoTriage labels found.")
        return

    print(f"Found {len(triage_labels)} AutoTriage label(s):")
    for l in triage_labels:
        print(f"  - {l['name']} ({l['id']})")

    # 2. For each label, find all emails that have it and remove it
    total_untagged = 0
    for label in triage_labels:
        label_id = label["id"]
        label_name = label["name"]

        # Fetch all message IDs with this label (paginated)
        msg_ids = []
        page_token = None
        while True:
            kwargs = {"userId": "me", "labelIds": [label_id], "maxResults": 500}
            if page_token:
                kwargs["pageToken"] = page_token
            resp = service.users().messages().list(**kwargs).execute()
            msgs = resp.get("messages", [])
            msg_ids.extend(m["id"] for m in msgs)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        if msg_ids:
            # Remove label in batches of 1000 (Gmail batchModify limit)
            for i in range(0, len(msg_ids), 1000):
                batch = msg_ids[i:i + 1000]
                service.users().messages().batchModify(
                    userId="me",
                    body={"ids": batch, "removeLabelIds": [label_id]},
                ).execute()
            total_untagged += len(msg_ids)
            print(f"  Removed '{label_name}' from {len(msg_ids)} email(s).")
        else:
            print(f"  '{label_name}' had no emails.")

        # 3. Delete the label itself
        service.users().labels().delete(userId="me", id=label_id).execute()
        print(f"  Deleted label '{label_name}'.")

    print(f"\nDone. {total_untagged} email(s) untagged, {len(triage_labels)} label(s) deleted.")


if __name__ == "__main__":
    main()
