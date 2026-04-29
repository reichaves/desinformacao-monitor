# Disinformation Monitor

> **Status: 🚧 Beta Version**

[![GitHub Pages](https://img.shields.io/badge/Live%20Report-GitHub%20Pages-red)](https://reichaves.github.io/desinformacao-monitor/)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue)](https://github.com/reichaves/desinformacao-monitor)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Gemini](https://img.shields.io/badge/AI-Gemini%203.1%20Flash%20Lite-orange)](https://aistudio.google.com)
[![Actions](https://img.shields.io/badge/Automation-GitHub%20Actions%207PM%20BRT-lightgrey)](https://github.com/reichaves/desinformacao-monitor/actions)

Automated pipeline that monitors **disinformation, attacks on the press, and anti-democratic discourse in Brazil** on YouTube and TikTok — with AI analysis (Gemini), an interactive report published on GitHub Pages, and daily execution via GitHub Actions.

**Author:** Reinaldo Chaves ([reichaves@gmail.com](mailto:reichaves@gmail.com)) · [@reichaves](https://github.com/reichaves)

**Live report:** https://reichaves.github.io/desinformacao-monitor/

---

## How it works

```
┌─────────────────────────────────────────────────────────┐
│  config/keywords.json  (100+ hashtags and terms)        │
└─────────────────────┬───────────────────────────────────┘
                      │
          ┌───────────▼────────────┐
          │   Collectors           │
          │  YouTube (yt-dlp)      │  → search via ytsearchN:query
          │  TikTok  (Playwright)  │  → navigates hashtag pages
          └───────────┬────────────┘
                      │ VideoMetadata
          ┌───────────▼────────────┐
          │   Download / Fallback  │
          │  yt-dlp + ffmpeg       │  → video + MP3
          │  No-download fallback: │
          │    YouTube Transcript  │  → captions via API
          │    API + thumbnail     │
          │    TikTok: Playwright  │  → page text +
          │    page screenshot     │    screenshot
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │   Processors           │
          │  Transcription (Gemini)│  → audio → text
          │  Visual analysis       │  → frames → signals
          │  Content analysis      │  → classification + severity
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │   Storage              │
          │  Local (data/)         │  → JSON per video + summary
          │  Google Drive          │  → optional
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │   HTML Report          │
          │  docs/index.html       │  → GitHub Pages
          └────────────────────────┘
```

### What the pipeline does on each run

1. **Collects** up to 20 videos on YouTube and TikTok using 100+ Brazilian disinformation hashtags and terms
2. **Downloads + extracts** audio (MP3) via yt-dlp + ffmpeg
   - *Automatic fallback:* if download is blocked (datacenter IPs), uses YouTube's captions API (no download required) and Playwright scraping for TikTok
3. **Transcribes** audio word-by-word via Gemini File API (or pre-fetched captions in fallback mode)
4. **Visual analysis** of frames/thumbnails — Gemini detects on-screen text, visual disinformation indicators, personalities, and symbols
5. **Conservative AI classification**: disinformation type (`health`, `electoral`, `institutional`, `media`, `other`, `none`), severity 0–5, confidence score (0–100), false claims, factual counter-narrative. The model is calibrated to minimize false positives — most videos return `none/0`
6. **Interactive HTML report** with filters, charts, and high-severity alerts
7. **Automatic commit** of the updated report to GitHub Pages

---

## Project structure

```
desinformacao-monitor/
├── pipeline.py                          ← Main orchestrator (entry point)
├── setup_drive_auth.py                  ← OAuth refresh token generator (one-time use)
├── requirements.txt
├── config/
│   └── keywords.json                    ← Monitored hashtags and terms (editable)
├── src/
│   ├── collector/
│   │   ├── base_collector.py            ← Abstract base class + VideoMetadata dataclass
│   │   ├── youtube_collector.py         ← Search + download + transcript/thumb fallback
│   │   └── tiktok_collector.py          ← Playwright scraping + download + fallback
│   ├── processor/
│   │   ├── screenshot_extractor.py      ← ffmpeg: 1 frame every N seconds
│   │   ├── audio_transcriber.py         ← Gemini File API: audio → text
│   │   ├── visual_analyzer.py           ← Gemini vision: frames → disinformation signals
│   │   └── content_analyzer.py          ← Gemini text: structured classification
│   ├── storage/
│   │   ├── local_storage.py             ← Per-run directories + JSON output
│   │   └── drive_uploader.py            ← OAuth 2.0 upload to Google Drive
│   └── reporter/
│       ├── html_generator.py            ← Renders Jinja2 → HTML
│       └── templates/
│           └── index_template.html      ← Chart.js + Tailwind (zero build)
├── docs/
│   └── index.html                       ← Published report (GitHub Pages)
├── tests/                               ← Unit tests (pytest)
└── .github/
    └── workflows/
        └── daily_monitor.yml            ← Cron 22:00 UTC = 19:00 BRT
```

---

## Quick start (local)

### Prerequisites

| Tool | Version | Installation |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| ffmpeg | any | `apt install ffmpeg` / `brew install ffmpeg` / [ffmpeg.org](https://ffmpeg.org) |
| Git | 2.x+ | [git-scm.com](https://git-scm.com) |
| Gemini API key | — | [aistudio.google.com](https://aistudio.google.com) (free tier available) |

### Installation

```bash
# Clone the repository
git clone https://github.com/reichaves/desinformacao-monitor.git
cd desinformacao-monitor

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate         # Linux/Mac
.venv\Scripts\activate            # Windows

# Install Python dependencies
pip install -r requirements.txt

# Install the Playwright browser (required for TikTok)
playwright install chromium
```

### Configuration

Create a `.env` file at the project root:

```env
# Required
GEMINI_API_KEY=your_key_here

# Optional — Gemini model (default: gemini-3.1-flash-lite-preview)
GEMINI_MODEL=gemini-3.1-flash-lite-preview

# Optional — volume control
MAX_VIDEOS_PER_RUN=20
HOURS_BACK=24

# Optional — cookies to avoid bot-detection blocks
YOUTUBE_COOKIES_FILE=/path/to/youtube_cookies.txt
TIKTOK_COOKIES_FILE=/path/to/tiktok_cookies.txt

# Optional — Google Drive
ENABLE_GOOGLE_DRIVE=false
GOOGLE_DRIVE_CLIENT_ID=
GOOGLE_DRIVE_CLIENT_SECRET=
GOOGLE_DRIVE_REFRESH_TOKEN=
GOOGLE_DRIVE_FOLDER_ID=
```

### Run

```bash
# Linux/Mac — load .env and run
export $(grep -v '^#' .env | xargs) && python pipeline.py

# Windows (PowerShell)
Get-Content .env | Where-Object { $_ -notmatch '^#' -and $_ -ne '' } | ForEach-Object {
    $parts = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($parts[0], $parts[1])
}
python pipeline.py
```

The report will be generated at `docs/index.html`. Open it in a browser to view.

### Tests

```bash
python -m pytest tests/ -v
```

---

## Deploy on GitHub Actions (daily automation)

See the [full Deploy Guide](DEPLOY_GUIDE.md) for step-by-step instructions.

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `GEMINI_API_KEY` | Gemini API key — required |
| `YOUTUBE_COOKIES` | Contents of YouTube `cookies.txt` (Netscape format) |
| `TIKTOK_COOKIES` | Contents of TikTok `cookies.txt` (Netscape format) |
| `GOOGLE_DRIVE_CLIENT_ID` | OAuth Client ID — only if using Drive |
| `GOOGLE_DRIVE_CLIENT_SECRET` | OAuth Client Secret — only if using Drive |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | OAuth Refresh Token (generated by `setup_drive_auth.py`) |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive folder ID |

The workflow runs every day at **7:00 PM (Brasília time / BRT)** and:
- Collects videos
- Analyses them with Gemini
- Commits the updated `docs/index.html` to the repository
- GitHub Pages publishes it automatically

> **Note:** If you have a `GEMINI_MODEL` GitHub Variable set, it overrides the code default. To use `gemini-3.1-flash-lite-preview`, either delete the variable or update its value.

---

## Adapting to other contexts

### Changing monitored keywords

Edit `config/keywords.json`. The structure is:

```json
{
  "search_queries_youtube": ["specific search", "another search"],
  "search_queries_tiktok": ["hashtag1", "hashtag2"],
  "hashtags": ["#example", "#another"],
  "terms": ["free term", "another term"]
}
```

Changes take effect on the next run.

### Changing the analysis language or context

The analysis prompt is in `src/processor/content_analyzer.py`, in the `_ANALYSIS_PROMPT_TEMPLATE` variable. Rewrite the prompt to adapt it to your context (another country, another content type, another language).

### Changing the Gemini model

Set `GEMINI_MODEL` as an environment variable or GitHub Variable. Compatible models: `gemini-3.1-flash-lite-preview`, `gemini-2.0-flash`, `gemini-1.5-pro`, etc.

### Adding a new platform

1. Create `src/collector/new_platform_collector.py` inheriting from `BaseCollector`
2. Implement `search()` and `download()`
3. Instantiate and add it to the processing loop in `pipeline.py`

---

## Known limitations (Beta)

- **Downloads blocked on GitHub Actions:** Datacenter IPs are blocked by YouTube and TikTok. The pipeline uses automatic fallback — YouTube's captions API (`youtube-transcript-api`) and Playwright scraping for TikTok — but analysis is less rich than with full audio.
- **Date filtering via `ytsearch`:** Search uses `ytsearch:` + `--dateafter` + post-collection hour-level filter by `published_at`. In `--flat-playlist` mode, the `upload_date` field (YYYYMMDD) is parsed as a fallback when the Unix `timestamp` is unavailable.
- **TikTok timestamps via snowflake ID:** TikTok video IDs are snowflake IDs — the creation timestamp is decoded from the upper 32 bits. Works in practice with ~1 second precision.
- **Conservatively calibrated by design:** The Gemini prompt is tuned to minimize false positives. Most keyword-matched videos are not disinformation — they merely mention the monitored topics. The `confidence` field (0–100) indicates model certainty in the classification.
- **Severity requires human review:** The 0–5 classification is an automated estimate. Never publish results without editorial review.
- **Gemini quota:** With 20 videos/day using `gemini-3.1-flash-lite-preview`, estimated cost < USD 2/month on the paid plan.

---

## Legal disclaimer

This project collects and analyses publicly available content from YouTube and TikTok exclusively for **journalistic research and disinformation monitoring** purposes. The severity score assigned by the AI model is an automated estimate and **requires human editorial review before any publication**. The author is not responsible for misuse of this software.

---

**Author:** Reinaldo Chaves · [reichaves@gmail.com](mailto:reichaves@gmail.com) · [github.com/reichaves](https://github.com/reichaves)
