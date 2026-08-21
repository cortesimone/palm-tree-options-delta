# Palm Tree Options Delta

CLI tools for equity options research via the Alpaca Markets API: find puts near a target delta, price ATM straddles across upcoming expirations, and push results to Google Sheets when the market is open.

## Configuration Paradigm

The application uses a **hierarchical configuration system** that separates local development from production deployment:

```
Loading priority (highest → lowest):
  1. Environment variables  (os.environ)
  2. secrets/.env           (deployed with the application)
  3. config/settings.py     (hardcoded production defaults)
```

This means:

- **Local development**: Set environment variables to override any value without touching committed files.
- **Remote deployment**: Only `secrets/.env` (and env vars on the server) controls behavior. `config/settings.py` provides a stable production baseline.
- **No leakage**: Local `.env` files are gitignored. Production defaults in `config/settings.py` are source-controlled and never overwritten.

### Setting up credentials

```bash
mkdir -p secrets
cp .env.example secrets/.env
```

Edit `secrets/.env` and fill in your credentials. **Never commit `secrets/.env` or any file containing API keys.**

### Overriding values

**Via environment variables** (highest priority, works locally and on the server):

```bash
export ALPACA_API_KEY=your_key
export GOOGLE_SHEET_ID=your_sheet_id
export ENVIRONMENT=local   # or production
```

**Via `secrets/.env`** (overrides defaults, committed to the server via git):

```env
ALPACA_API_KEY=your_key
GOOGLE_SHEET_ID=your_sheet_id
GSHEET_TAB_NAME=CSP
```

**Via `config/settings.py`** (production baseline, source-controlled):

Edit `config/settings.py` to change default values that apply to all environments. This is the recommended way to set production defaults that should be version-controlled.

## Setup

1. Copy the example environment file:

```bash
mkdir -p secrets
cp .env.example secrets/.env
```

2. Edit `secrets/.env` and fill in your API key and secret:

```bash
ALPACA_API_KEY=your_api_key
ALPACA_API_SECRET=your_api_secret
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 find_near_delta_puts.py [SYMBOL] [TARGET_DELTA] [COUNT]
```

### Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `symbol` | `TSLA` | Stock ticker symbol |
| `target_delta` | `-0.18` | Target put delta (negative for puts) |
| `count` | `4` | Number of results to return |

### Options

| Flag | Description |
|------|-------------|
| `-s N`, `--skip N` | Skip N Fridays ahead (0 = next Friday, 1 = following Friday, etc.) |
| `-d DATE`, `--date DATE` | Exact expiration date in `YYYY-MM-DD` format |

### Examples

```bash
# Next Friday, target delta -0.18, 4 results
python3 find_near_delta_puts.py TSLA -0.18 4

# Skip 1 Friday (2nd Friday out)
python3 find_near_delta_puts.py TSLA -0.18 4 -s 1

# Skip 2 Fridays (3rd Friday out)
python3 find_near_delta_puts.py TSLA -0.18 4 --skip 2

# Specific monthly expiration
python3 find_near_delta_puts.py AAPL -0.25 3 -d 2026-09-18

# Quarterly expiration
python3 find_near_delta_puts.py AAPL -0.25 3 --date 2026-12-18

# Default symbol and parameters
python3 find_near_delta_puts.py
```

### Output

The command prints a table with the following columns:

- **Strike** — Option strike price
- **Delta** — Option delta
- **Theta** — Option theta (time decay)
- **Premium** — Current premium/candle close
- **Expiry** — Expiration date
- **Symbol** — Full option chain symbol

## Deployment to Remote Server

On the remote Ubuntu server:

1. Clone/pull the repository.
2. Copy `.env.example` to `secrets/.env` and fill in credentials.
3. Place the Google service-account JSON key in `secrets/google-credentials.json`.
4. Set any server-specific overrides as environment variables (e.g., in `~/.bashrc` or systemd service).
5. Run `python3 upload_to_sheet.py` or set up the cron job with `check_market_and_upload.sh`.

Updates are applied by pulling the repository — `secrets/.env` and credentials are **not** version-controlled and remain untouched.

## File Structure

```
├── .env.example              # Template — copy to secrets/.env
├── .gitignore
├── config/
│   ├── __init__.py           # Hierarchical config loader
│   └── settings.py           # Production defaults (source-controlled)
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