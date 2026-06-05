# Deployment Guide

This guide covers deploying the intelligence dashboard to Streamlit Cloud. For basic setup, see [README.md](../README.md).

## Prerequisites

- GitHub account
- Streamlit Cloud account (free at [share.streamlit.io](https://share.streamlit.io))
- At least one LLM provider key (any one of the three is enough; configure more for failover resilience)

## Environment Variables

The dashboard requires **at least one** LLM provider key. The client tries them in failover order, so configuring more than one improves resilience.

| Variable | Required | Purpose |
|----------|----------|---------|
| `CEREBRAS_API_KEY` | One of three | Primary provider by default. |
| `GROQ_API_KEY` | One of three | Second in chain. |
| `OPENROUTER_API_KEY` | One of three | Last-resort failover. |
| `LLM_PRIMARY_PROVIDER` | Optional | Override primary (default `cerebras`). |
| `LLM_TEMPERATURE` | Optional | Default `0.3`. |
| `LLM_MAX_TOKENS` | Optional | Default `4096`. |

### Local Development (.env file)

Create a `.env` file in the project root:

```bash
CEREBRAS_API_KEY=your-actual-cerebras-key
GROQ_API_KEY=your-actual-groq-key
OPENROUTER_API_KEY=your-actual-openrouter-key
LLM_PRIMARY_PROVIDER=cerebras
```

**Security:** The `.env` file is already in `.gitignore` and will never be committed to Git.

### Streamlit Cloud (Secrets)

In Streamlit Cloud app settings, add this to the Secrets section:

```toml
CEREBRAS_API_KEY = "your-actual-cerebras-key"
GROQ_API_KEY = "your-actual-groq-key"
OPENROUTER_API_KEY = "your-actual-openrouter-key"
LLM_PRIMARY_PROVIDER = "cerebras"
```

## GitHub Push

```bash
# Verify .env is not tracked
git status  # Should NOT show .env

# Add and commit all files
git add .
git commit -m "Initial commit"

# Create repo on GitHub, then push
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
git branch -M main
git push -u origin main
```

## Streamlit Cloud Deployment

### Step 1: Connect GitHub

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Authorize Streamlit to access your repositories

### Step 2: Create New App

1. Click **"New app"**
2. Select your repository
3. Set **Branch:** `main`
4. Set **Main file path:** `dashboard.py`

### Step 3: Configure Secrets

1. Click **"Advanced settings"**
2. In the **Secrets** box, paste at least one provider key:

```toml
CEREBRAS_API_KEY = "your-actual-cerebras-key"
GROQ_API_KEY = "your-actual-groq-key"
OPENROUTER_API_KEY = "your-actual-openrouter-key"
LLM_PRIMARY_PROVIDER = "cerebras"
```

3. Click **"Deploy"**

### Step 4: Wait for Deployment

- Initial deployment takes 5-10 minutes (spaCy model download)
- Streamlit will automatically restart when complete
- Your app URL: `https://YOUR-USERNAME-YOUR-REPO.streamlit.app`

## Data Management

The dashboard requires these files in `outputs/`:
- `latest_competitor_news.json`
- `daily_analysis.json`
- `daily_briefing.md`

### Option A: Commit Initial Data (Recommended)

Run locally before first deployment:

```bash
python main.py
python analysis.py
git add outputs/
git commit -m "Add initial data"
git push
```

This ensures the dashboard has data immediately after deployment.

### Option B: Generate Data After Deployment

If you don't commit data files, users must run `main.py` and `analysis.py` locally first, then commit the generated files.

## Updating Data

To refresh the intelligence data:

```bash
# Run locally
python main.py
python analysis.py

# Commit and push
git add outputs/
git commit -m "Update intelligence data - $(date +%Y-%m-%d)"
git push

# Streamlit Cloud auto-redeploys within 1-2 minutes
```

## Troubleshooting

### "spaCy model not found"

The `setup.sh` script should automatically download the model. If it fails, check Streamlit Cloud logs.

**Fallback:** Add this line to `requirements.txt`:

```
https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl
```

### "No data available" in dashboard

Run `main.py` and `analysis.py` locally, then commit the `outputs/` files to GitHub.

### "Rate limit exceeded (429)"

Each provider has its own quota. The client retries with exponential backoff and then fails over to the next provider in the chain. Check quotas at the dashboard for each provider you've configured.

Run `python scripts/check_models.py` to verify which providers are currently configured for your environment.

### Code changes not updating

Streamlit Cloud caches deployments. Force a rebuild:
1. Go to your app settings
2. Click "Reboot app"
3. Wait 1-2 minutes for redeployment

## Security Checklist

Before deploying:

- Verify `.env` is NOT in `git status`
- Confirm `.env` is in `.gitignore`
- Set GitHub repository to **Private** (recommended)
- API key is in Streamlit Cloud Secrets, not in code
- Never commit API keys to Git

## Monitoring

- **Streamlit Cloud Logs:** Check the app admin panel for errors
- **API Usage:** Monitor quota at the dashboard of each provider you've configured
- **Auto-redeploy:** Streamlit Cloud automatically redeploys on every `git push`
- **Keep-alive:** `.github/workflows/keep_alive.yml` pings the live app every 2 days with headless Chromium to prevent the 7-day idle deactivation

## Quick Reference Commands

```bash
# Local testing
streamlit run dashboard.py

# Update data and deploy
python main.py && python analysis.py && git add outputs/ && git commit -m "Update data" && git push

# Check environment
cat .env  # Local
# Streamlit Cloud: App settings → Secrets
```
