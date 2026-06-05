# iGaming Competitive Intelligence Dashboard

A competitive intelligence system for Clarion Events (ICE/iGB) that tracks competitor news coverage, identifies content gaps, and surfaces commercial opportunities using AI-powered analysis and spaCy NER entity extraction.

[![Tests](https://img.shields.io/badge/tests-474%20passed-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.11-blue)](requirements.txt)
[![Streamlit](https://img.shields.io/badge/streamlit-1.x-red)](app/dashboard.py)

## Live Dashboard

**Production:** [igaming-competitor-newsfeed.streamlit.app](https://igaming-competitor-newsfeed.streamlit.app)

## What It Does

- Aggregates news from **17 iGaming sources** (8 competitors + 9 internal brands)
- Uses **Llama 3.3 70B** via a Cerebras → Groq → OpenRouter failover chain to identify strategic content gaps
- Extracts entities (companies, locations, topics) with **spaCy NER**
- Presents insights through an interactive **Streamlit dashboard**
- Runs automatically at **8am GMT daily** via GitHub Actions
- Stays warm on Streamlit Cloud via a **keep-alive Playwright workflow** every 2 days

## Quick Start

```bash
# Clone and setup
git clone https://github.com/pravindurgani/igaming-intelligence-dashboard.git
cd igaming-intelligence-dashboard
make setup

# Configure at least one LLM provider key (Cerebras recommended for speed + free tier)
cp .env.example .env
# Edit .env: set CEREBRAS_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY

# Run pipeline and launch dashboard
make pipeline
make dashboard
```

Or use the all-in-one runner:
```bash
python run_pipeline.py  # Runs everything and opens dashboard
```

## Dashboard Tabs

| Tab | Purpose | For |
|-----|---------|-----|
| **AI Briefing** | Executive summary, market trends, strategic gaps | Leadership, Content Directors |
| **News Feed** | Searchable article browser with filters | Journalists, Researchers |
| **Intelligence Battleground** | NER-based comparative analytics | Marketing, Sales, CI Analysts |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  scripts/main.py │────▶│scripts/analysis.py│────▶│ app/dashboard.py │
│  (News Scraping) │     │   (AI Analysis)   │     │   (Streamlit)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
   news_history.csv      daily_analysis.json      Interactive UI
   latest_news.json      daily_briefing.md        with NER charts
```

## Data Sources

### Competitor Sources (8)
SBC News, iGaming Future, Next.io, SiGMA World, EGR Global, CDC Gaming, Global Gaming Insider, iGaming Today

### Internal Sources (9)
iGaming Business, iGB Affiliate, GGB Magazine, Gambling Insider, Game Lounge, Gaming and Co, North Star Network, iGaming Afrika, iGaming Expert

## Project Structure

```
├── app/dashboard.py          # Streamlit dashboard (v1.0.0)
├── scripts/
│   ├── main.py               # News aggregation
│   └── analysis.py           # AI gap analysis
├── src/
│   ├── search.py             # Unified search engine
│   ├── taxonomy.py           # Entity classification
│   └── gemini_ner_analysis.py # AI-powered features
├── tests/                    # 474 tests (+ 9 opt-in LLM evals)
├── .github/workflows/
│   ├── ci.yml                # CI: lint + test
│   └── scheduled_pipeline.yml # Daily 8am GMT run
├── scheduler.py              # Local scheduler daemon
├── Makefile                  # Build automation
└── requirements.txt          # Dependencies
```

## Makefile Commands

```bash
make setup           # Create venv and install dependencies
make test            # Run all tests (474 tests, 9 LLM evals skipped without keys)
make lint            # Run ruff linter
make dashboard       # Start Streamlit dashboard
make pipeline        # Run full pipeline
make scheduler       # Start background scheduler (8am GMT)
make scheduler-once  # Run pipeline once immediately
```

## Environment Variables

At least one LLM provider key is required. The client tries them in failover order.

| Variable | Required | Description |
|----------|----------|-------------|
| `CEREBRAS_API_KEY` | One of three | Cerebras Llama 3.3 70B (~2600 tok/s, 1M tokens/day free). Primary by default. |
| `GROQ_API_KEY` | One of three | Groq Llama 3.3 70B Versatile (14.4k req/day free). |
| `OPENROUTER_API_KEY` | One of three | OpenRouter Llama 3.3 70B free tier (last-resort failover). |
| `LLM_PRIMARY_PROVIDER` | No | Override primary (`cerebras` / `groq` / `openrouter`). Default `cerebras`. |
| `LLM_TEMPERATURE` | No | Default `0.3`. |
| `LLM_MAX_TOKENS` | No | Default `4096`. |
| `DEBUG_MODE` | No | Set to `1` for debug features. |

Run `python scripts/check_models.py` to verify which providers are configured.

## Automated Scheduling

### GitHub Actions (Recommended)
The pipeline runs automatically at **8am GMT daily** via `.github/workflows/scheduled_pipeline.yml`. A separate `keep_alive.yml` workflow visits the live Streamlit app every 2 days so it never goes idle past the 7-day deactivation window.

Requirements:
1. Add at least one of `CEREBRAS_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` to repository secrets
2. Enable "Read and write permissions" for workflows

### Local Scheduler
```bash
make scheduler       # Runs daily at 8am GMT
make scheduler-once  # Run once immediately
```

## Health Check

Access `/?health=check` to verify the dashboard is running:
```
https://your-app.streamlit.app/?health=check
```

## Testing

```bash
make test                    # All tests
pytest tests/ -v             # Verbose output
pytest tests/ -k "search"    # Run specific tests
```

## Key Features

- **Smart Deduplication** - Tracks article history, prevents duplicates
- **Evidence Linking** - Each gap backed by supporting article references
- **Unified Search** - Consistent search across all tabs
- **Session State** - Filters persist during navigation
- **Lazy Loading** - AI features load on-demand for performance
- **Cost Optimization** - Pre-aggregation reduces API costs by 85%

## Troubleshooting

**spaCy model not found:**
```bash
python -m spacy download en_core_web_sm
```

**LLM provider rate limit:**
- Automatic exponential-backoff retry built in; on persistent 429s the chain fails over to the next provider.
- Check quota at [Cerebras Cloud](https://cloud.cerebras.ai/) / [Groq Console](https://console.groq.com/) / [OpenRouter](https://openrouter.ai/keys).

**Widget warning on reload:**
- Fixed in v1.0.0 - session state properly managed

## Documentation

- [CHANGELOG.md](CHANGELOG.md) - Version history
- [docs/audits/](docs/audits/) - Technical audits
- [docs/guides/](docs/guides/) - User guides

## License

Proprietary - Clarion Events

---

**Version:** 1.1.0 | **Tests:** 474 passed | **Last Updated:** 2026-06-05
