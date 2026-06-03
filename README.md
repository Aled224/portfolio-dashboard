# Portfolio dashboard (Streamlit)

A small, generic Streamlit dashboard that reads its data from a separate
**private** GitHub repository via the GitHub API. This repository contains
**only the program**: no personal data, no amounts, no passwords, no keys.

## Configuration (Streamlit Cloud → Settings → Secrets)
```
app_password  = "a-password"
github_token  = "a-token-with-contents-read-write-on-the-data-repo"
github_repo   = "USER/private-data-repo"
github_branch = "main"
data_path     = "data.json"
```

## Scheduled price update (GitHub Actions → Secrets)
- `DATA_TOKEN` — token with Contents read/write on the private data repo
- `DATA_REPO` — `USER/private-data-repo`
- `EMAIL_USER`, `EMAIL_APP_PASSWORD`, `EMAIL_TO`, `APP_URL` — optional, for the email report

## Files
- `streamlit_app.py` — the dashboard UI (password-gated)
- `github_store.py` — read/write the data file via the GitHub API
- `prices.py` — fetch market prices from Yahoo Finance and recompute values
- `update_prices.py` + `.github/workflows/update.yml` — weekly/on-demand updater
