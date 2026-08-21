# Palm Tree Options Delta

CLI tools for equity options research via the Alpaca Markets API: find puts near a target delta, price ATM straddles across upcoming expirations, and push results to Google Sheets when the market is open.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up credentials

```bash
mkdir -p secrets
cp .env.example secrets/.env
```

Edit `secrets/.env` with your credentials:

```env
ALPACA_API_KEY=your_api_key
ALPACA_API_SECRET=your_api_secret
GSHEET_ACCESS_KEY=path/to/google-credentials.json
GSHEET_ID=your_tab_name
```

Place your Google service-account JSON file in `secrets/` (e.g. `secrets/google-credentials.json`). **Never commit `secrets/.env` or any credentials file.**

### 3. Run a command

```bash
python3 find_near_delta_puts.py TSLA -0.18 4
```

---

## Tools

### Find near-delta puts

```bash
python3 find_near_delta_puts.py [SYMBOL] [TARGET_DELTA] [COUNT]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `symbol` | `TSLA` | Stock ticker symbol |
| `target_delta` | `-0.18` | Target put delta (negative for puts) |
| `count` | `4` | Number of results to return |

| Flag | Description |
|------|-------------|
| `-s N`, `--skip N` | Skip N Fridays ahead (0 = next Friday, 1 = following Friday, etc.) |
| `-d DATE`, `--date DATE` | Exact expiration date in `YYYY-MM-DD` format |

```bash
# Next Friday, target delta -0.18, 4 results
python3 find_near_delta_puts.py TSLA -0.18 4

# Skip 1 Friday (2nd Friday out)
python3 find_near_delta_puts.py TSLA -0.18 4 -s 1

# Specific monthly expiration
python3 find_near_delta_puts.py AAPL -0.25 3 -d 2026-09-18

# Default symbol and parameters
python3 find_near_delta_puts.py
```

**Output** — prints a table with: Strike, Delta, Theta, Premium, Expiry, Symbol.

### ATM straddle calculator

```bash
python3 atm_straddle.py [SYMBOL]
```

Prices ATM straddles across upcoming expirations.

### Upload to Google Sheets

```bash
python3 upload_to_sheet.py [SYMBOL] [TARGET_DELTA] [COUNT]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `symbol` | `TSLA` | Stock ticker symbol |
| `target_delta` | `-0.18` | Target put delta |
| `count` | `4` | Number of results |

| Flag | Description |
|------|-------------|
| `-s N`, `--skip N` | Skip N Fridays ahead (0 = next Friday, 1 = following Friday) |
| `-d DATE`, `--date DATE` | Exact expiration date in `YYYY-MM-DD` format |
| `--both` | Upload both upcoming and following Friday into the same tab |
| `--tab NAME` | Target tab name (default: `CSP`) |
| `--spreadsheet-id ID` | Google Spreadsheet ID (overrides env var) |

```bash
# Next Friday to CSP tab (default)
python3 upload_to_sheet.py TSLA -0.18 4

# Following Friday
python3 upload_to_sheet.py TSLA -0.18 4 --skip 1

# Both Fridays stacked in one tab
python3 upload_to_sheet.py TSLA -0.18 4 --both

# Specific expiration date
python3 upload_to_sheet.py AAPL -0.25 3 --date 2026-09-18

# Custom tab and spreadsheet
python3 upload_to_sheet.py TSLA -0.18 4 --tab PUTS --spreadsheet-id "1ABC...xyz"
```

Uploads a formatted table with header (underlying price, expiration, target delta), sorted by strike descending, to the specified Google Sheet tab. Overwrites existing content in the tab. Creates the tab if it doesn't exist.

### Market check + auto-upload (cron)

```bash
bash check_market_and_upload.sh
```

Checks if the Alpaca market is open, and if so, runs `upload_to_sheet.py` with the configured symbol/delta/count. Designed for cron jobs. Logs to `market_check.log`.

---

## Configuration

The app uses a hierarchical config system. Values are resolved in this order (highest priority first):

1. **Environment variables** — `export ALPACA_API_KEY=...`
2. **`.env.{APP_ENV}`** — e.g. `.env.production` or `.env.local`
3. **`secrets/.env`** — deployed with the app
4. **`.env`** (project root) — local machine overrides
5. **`config/defaults.json`** — committed defaults

Set the environment with `APP_ENV=local` (default) or `APP_ENV=production`.

### Cron defaults

The shell script reads these from the config (defaults shown):

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON_SYMBOL` | `SPCX` | Ticker symbol |
| `CRON_TARGET_DELTA` | `-0.18` | Target put delta |
| `CRON_COUNT` | `4` | Number of results |
| `CRON_USE_BOTH` | `False` | Upload both Fridays |

Override via environment variables or `.env.production`.

---

## File Structure

```
├── .env.example              # Template — copy to secrets/.env
├── .gitignore
├── config/
│   ├── config.py             # Hierarchical config loader
│   └── defaults.json         # Committed default values
├── secrets/
│   ├── .env                  # Credentials (gitignored)
│   └── google-credentials.json  # Google service account (gitignored)
├── atm_straddle.py           # ATM straddle calculator
├── find_near_delta_puts.py   # Find puts near target delta
├── upload_to_sheet.py        # Upload results to Google Sheets
├── check_market_and_upload.sh  # Cron job: check market + upload
└── requirements.txt
```

## Notes

- `--skip` and `--date` are mutually exclusive.
- The script uses the Alpaca `indicative` feed, which returns greeks for actively traded strikes.
- Both `secrets/.env` and `secrets/google-credentials.json` are gitignored and should never be committed.