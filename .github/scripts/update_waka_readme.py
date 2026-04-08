#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_URL = "https://wakatime.com/api/v1/users/current/stats/last_7_days"
README_PATH = pathlib.Path(os.environ.get("README_PATH", "README.md"))
SECTION_NAME = os.environ.get("SECTION_NAME", "waka")
MAX_ITEMS = int(os.environ.get("WAKATIME_MAX_ITEMS", "5"))
API_KEY = os.environ.get("WAKATIME_API_KEY")

START_MARKER = f"<!--START_SECTION:{SECTION_NAME}-->"
END_MARKER = f"<!--END_SECTION:{SECTION_NAME}-->"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def fetch_stats() -> dict:
    if not API_KEY:
        fail("WAKATIME_API_KEY is not set")

    auth = base64.b64encode(API_KEY.encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        API_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "User-Agent": "nunoiland-waka-readme",
        },
    )

    last_data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            fail(f"WakaTime API request failed with {exc.code}: {body}")
        except urllib.error.URLError as exc:
            fail(f"Could not reach WakaTime API: {exc.reason}")

        data = payload.get("data", {})
        last_data = data
        if data.get("is_up_to_date", True):
            return data
        if attempt < 2:
            time.sleep(5)

    if last_data is None:
        fail("WakaTime API returned no data")
    return last_data


def format_percent(value: float | int | None) -> str:
    if value is None:
        return "0%"
    rounded = round(float(value), 1)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def format_timestamp(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def top_items(items: list[dict]) -> list[dict]:
    return [item for item in items if item.get("total_seconds", 0) > 0][:MAX_ITEMS]


def format_section(title: str, items: list[dict]) -> list[str]:
    if not items:
        return []
    lines = [f"**{title}**"]
    for item in items:
        name = item.get("name", "Unknown")
        text = item.get("text") or item.get("digital") or "0 secs"
        percent = format_percent(item.get("percent"))
        lines.append(f"- {name}: `{text}` ({percent})")
    return lines


def render(data: dict) -> str:
    total = data.get("human_readable_total_including_other_language") or data.get("human_readable_total") or "0 secs"
    daily_average = data.get("human_readable_daily_average_including_other_language") or data.get("human_readable_daily_average") or "0 secs"
    best_day = data.get("best_day") or {}

    lines = [
        f"- Last 7 days: `{total}`",
        f"- Daily average: `{daily_average}`",
    ]

    if best_day.get("date") and best_day.get("text"):
        lines.append(f"- Best day: `{best_day['date']}` (`{best_day['text']}`)")

    if data.get("timezone"):
        lines.append(f"- Timezone: `{data['timezone']}`")

    lines.append(f"- Updated: `{format_timestamp(data.get('modified_at'))}`")

    for title, key in (
        ("Languages", "languages"),
        ("Editors", "editors"),
        ("Projects", "projects"),
        ("Operating Systems", "operating_systems"),
    ):
        section_lines = format_section(title, top_items(data.get(key, [])))
        if section_lines:
            lines.append("")
            lines.extend(section_lines)

    return "\n".join(lines)


def update_readme(section_content: str) -> str:
    readme_text = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in readme_text or END_MARKER not in readme_text:
        fail(f"README markers {START_MARKER} and {END_MARKER} were not both found")

    replacement = f"{START_MARKER}\n{section_content}\n{END_MARKER}"
    pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)
    new_text, count = pattern.subn(replacement, readme_text, count=1)
    if count != 1:
        fail("Failed to update README WakaTime section")
    return new_text


def main() -> None:
    if not README_PATH.exists():
        fail(f"README not found at {README_PATH}")

    stats = fetch_stats()
    rendered = render(stats)
    new_text = update_readme(rendered)
    README_PATH.write_text(new_text, encoding="utf-8")
    print("README WakaTime section updated")


if __name__ == "__main__":
    main()
