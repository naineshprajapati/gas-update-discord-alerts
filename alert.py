import json
import os
from pathlib import Path

import feedparser
import requests

FEED_URL = os.environ["RSS_FEED_URL"]
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
ROLE_ID = os.environ["DISCORD_ROLE_ID"]
STATE_FILE = Path("last_seen.json")


def post_id(entry):
    return entry.get("id") or entry.get("guid") or entry.get("link")


def main():
    feed = feedparser.parse(FEED_URL)

    if feed.bozo and not feed.entries:
        raise RuntimeError(
            f"Unable to read RSS feed: {feed.bozo_exception}"
        )

    if not feed.entries:
        raise RuntimeError("RSS feed returned no posts.")

    entries = [e for e in feed.entries if post_id(e)]

    if not entries:
        raise RuntimeError("Feed entries have no usable IDs.")

    # First run: initialize without sending historical alerts.
    if not STATE_FILE.exists():
        STATE_FILE.write_text(
            json.dumps({"last_id": post_id(entries[0])}, indent=2)
            + "\n"
        )
        print("Initialized tracking; no alert sent.")
        return

    state = json.loads(STATE_FILE.read_text())
    last_id = state.get("last_id")

    # Nothing to do if the latest entry is already processed.
    if post_id(entries[0]) == last_id:
        print("No new posts.")
        return

    # Find entries newer than the last processed entry.
    new_entries = []

    for entry in entries:
        if post_id(entry) == last_id:
            break
        new_entries.append(entry)

    # If the previous post isn't in the feed, do not alert
    # on a potentially old tweet.
    if not any(post_id(e) == last_id for e in entries):
        print("Previous post not found in feed; skipping alerts.")
        return

    # Process oldest to newest so alerts arrive in order.
    for entry in reversed(new_entries):
        link = entry.get("link")
        if not link:
            continue

        response = requests.post(
            WEBHOOK_URL,
            json={
                "content": f"<@&{ROLE_ID}> New X post!\n{link}",
                "allowed_mentions": {
                    "parse": [],
                    "roles": [ROLE_ID],
                },
            },
            timeout=20,
        )
        response.raise_for_status()

        # Persist progress after each successful alert.
        STATE_FILE.write_text(
            json.dumps({"last_id": post_id(entry)}, indent=2)
            + "\n"
        )

        print(f"Alert sent for: {link}")


if __name__ == "__main__":
    main()
