import json
import os
import re
import html
from pathlib import Path

import feedparser
import requests

FEED_URL = os.environ["RSS_FEED_URL"]
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
ROLE_ID = os.environ["DISCORD_ROLE_ID"]
STATE_FILE = Path("last_seen.json")


def post_id(entry):
    return entry.get("id") or entry.get("guid") or entry.get("link")


def get_tweet_content(entry):
    """Extract tweet text from common RSS feed fields."""

    content = ""

    # Some RSS feeds provide the post content here.
    if entry.get("content"):
        content = entry["content"][0].get("value", "")

    # Fall back to summary or description.
    if not content:
        content = entry.get("summary", "") or entry.get("description", "")

    # Decode HTML entities and remove HTML tags.
    content = html.unescape(content)
    content = re.sub(r"<[^>]+>", "", content)
    content = re.sub(r"\s+", " ", content).strip()

    return content or "(Tweet content unavailable in RSS feed)"


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

    if post_id(entries[0]) == last_id:
        print("No new posts.")
        return

    new_entries = []

    for entry in entries:
        if post_id(entry) == last_id:
            break
        new_entries.append(entry)

    # Avoid alerting on potentially old posts if the previous
    # post is no longer present in the feed.
    if not any(post_id(e) == last_id for e in entries):
        print("Previous post not found in feed; skipping alerts.")
        return

    # Process oldest to newest.
    for entry in reversed(new_entries):
        link = entry.get("link")
        if not link:
            continue

        tweet_text = get_tweet_content(entry)

        message = (
            f"<@&{ROLE_ID}> **New gas update!**\n\n"
            f"{tweet_text}\n\n"
            f"{link}"
        )

        # Discord messages have a 2,000-character limit.
        if len(message) > 2000:
            message = message[:1990] + "…"

        response = requests.post(
            WEBHOOK_URL,
            json={
                "content": message,
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
