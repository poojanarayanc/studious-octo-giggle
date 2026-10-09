"""Daily AI news agent.

Searches the web for the past day's AI news from around the world, then writes
a Markdown digest to digests/YYYY-MM-DD.md. Optionally emails the digest.

Usage:
    ANTHROPIC_API_KEY=... python news_agent.py [--date YYYY-MM-DD] [--email]
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"
DIGEST_DIR = Path(__file__).parent / "digests"
MAX_PAUSE_RESUMES = 5

SYSTEM_PROMPT = """\
You are an AI-news editor producing a daily briefing for a reader who wants a
global view of artificial intelligence. Use web search and web fetch to find
what actually happened in the last 24-36 hours, then write the briefing.

Coverage - look beyond US tech press. Deliberately search for AI news from:
- North America, Europe (incl. EU AI Act / UK), China, India, Japan, South
  Korea, the Middle East, Africa, Latin America, Southeast Asia and Oceania.
- Topics: frontier model and product releases, research breakthroughs, policy
  and regulation, funding / M&A / business, chips and compute, open source,
  safety and ethics, notable real-world deployments.

Editorial rules:
- Only include stories published within the window; skip anything older.
- Verify each item against at least one credible source and link it.
- Merge duplicate coverage of the same event into one item.
- No hype; state facts, then one line on why it matters.
- If a story already appeared in the previous digest (provided below), only
  include it if there is a material new development, and say what changed.

Output ONLY the briefing in this Markdown format, nothing before or after:

# AI News Digest - {date}

## Top stories
3-5 most important items. For each:
### <Headline>
<2-3 sentence summary.> **Why it matters:** <one sentence.>
Sources: [Publication](url), [Publication](url)

## Around the world
Group by region (### Americas, ### Europe, ### Asia-Pacific,
### Middle East & Africa). 2-4 bullets each, format:
- **<Headline>** - <one-sentence summary>. ([Publication](url))
Omit a region only if you genuinely found nothing new for it.

## Research & open source
2-4 bullets in the same bullet format.

## Policy & regulation
2-4 bullets in the same bullet format.

## One to watch
One short paragraph on an emerging trend or upcoming event.
"""


def previous_digest(date: dt.date) -> str | None:
    """Return the most recent digest written before `date`, for de-duplication."""
    earlier = sorted(p for p in DIGEST_DIR.glob("*.md") if p.stem < date.isoformat())
    return earlier[-1].read_text(encoding="utf-8") if earlier else None


def build_user_message(date: dt.date) -> str:
    msg = f"Today is {date.isoformat()}. Produce today's AI news digest."
    prev = previous_digest(date)
    if prev:
        msg += (
            "\n\n<previous_digest>\n"
            f"{prev}\n"
            "</previous_digest>"
        )
    return msg


def generate_digest(client: anthropic.Anthropic, date: dt.date) -> str:
    messages: list = [{"role": "user", "content": build_user_message(date)}]
    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 25},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 15},
    ]

    for _ in range(MAX_PAUSE_RESUMES + 1):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            system=SYSTEM_PROMPT.replace("{date}", date.isoformat()),
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            tools=tools,
            messages=messages,
            # On a safety-classifier decline, re-run on Anthropic's recommended model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit its iteration limit; resend to continue.
            messages.append({"role": "assistant", "content": response.content})
            continue
        if response.stop_reason == "refusal":
            raise RuntimeError(f"Request was declined: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Digest was truncated (hit max_tokens).")

        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise RuntimeError("Model returned no digest text.")
        # Drop any preamble before the title heading.
        start = text.find("# AI News Digest")
        return text[start:] if start > 0 else text

    raise RuntimeError("Gave up: turn still paused after max resumes.")


def send_email(subject: str, body: str) -> None:
    """Send the digest via SMTP. Configure with SMTP_* and DIGEST_TO env vars."""
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    to = os.environ["DIGEST_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("DIGEST_FROM", user)
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=dt.date.fromisoformat,
                        default=dt.datetime.now(dt.timezone.utc).date())
    parser.add_argument("--email", action="store_true",
                        help="Also email the digest (needs SMTP_* env vars).")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    try:
        digest = generate_digest(client, args.date)
    except anthropic.RateLimitError as e:
        print(f"Rate limited, try again later: {e}", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"API error {e.status_code}: {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError as e:
        print(f"Could not reach the API: {e}", file=sys.stderr)
        return 1

    DIGEST_DIR.mkdir(exist_ok=True)
    out = DIGEST_DIR / f"{args.date.isoformat()}.md"
    out.write_text(digest + "\n", encoding="utf-8")
    print(f"Wrote {out}")

    if args.email:
        send_email(f"AI News Digest - {args.date.isoformat()}", digest)
        print(f"Emailed digest to {os.environ['DIGEST_TO']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
