# Daily AI News Agent

An agent that searches the web every day for AI news from around the world and
writes a sourced Markdown briefing to [`digests/`](digests/).

It uses Claude with the server-side web search and web fetch tools. Each digest
covers:

- **Top stories**: the 3–5 most important items, each with a "why it matters" line
- **Around the world**: Americas, Europe, Asia-Pacific, Middle East & Africa
- **Research & open source**
- **Policy & regulation**
- **One to watch**

Every item links to its sources. The agent reads the previous day's digest so
it doesn't repeat stories unless something new happened.

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python news_agent.py                    # writes digests/<today>.md
python news_agent.py --date 2026-10-08  # a specific date
```

## Run daily on GitHub Actions

`.github/workflows/daily-digest.yml` runs every day at 06:47 UTC and commits
the new digest to the repo. You can also start it by hand from the **Actions**
tab using "Run workflow".

1. Add the repository secret `ANTHROPIC_API_KEY` under
   Settings → Secrets and variables → Actions.
2. Optional, to get the digest by email: also add `SMTP_HOST`, `SMTP_PORT`
   (defaults to 587), `SMTP_USER`, `SMTP_PASSWORD`, and `DIGEST_TO`. For Gmail,
   use `smtp.gmail.com` with an app password.

## Customize

Edit `SYSTEM_PROMPT` in `news_agent.py` to change regions, topics, or the
format. To change the schedule, edit the `cron` line in the workflow.

Each run makes a few dozen web searches and fetches. Expect it to cost well
under a dollar a day.
