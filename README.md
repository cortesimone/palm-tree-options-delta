# Palm Tree Options Delta

CLI tools for equity options research via the Alpaca Markets API: find puts near a target delta, price ATM straddles across upcoming expirations, and push results to Google Sheets when the market is open.

## Setup

1. Copy the example environment file and add your Alpaca credentials:

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
pip install requests python-dotenv
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

## File Structure

```
straddle/
├── .env.example              # Example environment variables
├── .env                      # Your credentials (gitignored)
├── .gitignore
├── find_near_delta_puts.py   # Main script
└── secrets/
    ├── .env                  # Alpaca credentials (gitignored)
    ├── straddle.php          # PHP counterpart
    └── micro-instance-*.json # Service account key
```

## Notes

- `--skip` and `--date` are mutually exclusive.
- The script uses the Alpaca `indicative` feed, which returns greeks for actively traded strikes.
- Both `secrets/.env` and `.env` are gitignored and should never be committed.