import json
import os
from pathlib import Path

import feedparser
import requests

FEED_URL = os.environ["RSS_FEED_URL"]
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
ROLE_ID = os.environ["DISCORD_ROLE_ID"]
STATE_FILE = Path("last_seen.json")

def main():
    feed = feedparser.parse(FEED_URL)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Unable to read RSS feed: {feed.bozo_exception}")

    if not feed.entries:
        raise RuntimeError("RSS feed returned no posts.")

    def post_id(entry):
        return entry.get("id") or entry.get("guid") or entry.get("link")

    entries = [e for e in feed.entries if post_id(e)]

    if not entries:
        raise RuntimeError("Feed entries have no usable IDs.")

    latest_id = post_id(entries[0])

    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        last_id = state.get("last_id")

        if last_id == latest_id:
            print("No new posts.")
            return

        new_entries = []
        for entry in entries:
            if post_id(entry) == last_id:
                break
            new_entries.append(entry)

        if not any(post_id(e) == last_id for e in entries):
            # The saved post is no longer in the feed.
            # Avoid unexpectedly pinging for old posts.
            new_entries = entries[:1]

        for entry in reversed(new_entries):
            link = entry.get("link")
            if not link:
                continue

            response = requests.post(
                WEBHOOK_URL,
                json={
                    "content": (
                        f"<@&{ROLE_ID}> New X post!\n{link}"
                    ),
                    "allowed_mentions": {
                        "parse": [],
                        "roles": [ROLE_ID],
                    },
                },
                timeout=20,
            )
            response.raise_for_status()

    else:
        # First run: record the newest post without pinging
        # for historical posts.
        print("Initialized tracking; no alert sent.")

    STATE_FILE.write_text(
        json.dumps({"last_id": latest_id}, indent=2) + "\n"
    )

if __name__ == "__main__":
    main()
