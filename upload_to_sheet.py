#!/usr/bin/env python3
"""
Upload option data from find_near_delta_puts.py to a Google Spreadsheet tab.

Uses the Google Sheets API to locate the designated tab by name and overwrite
all existing content with the new output.

Usage:
    python3 upload_to_sheet.py [SYMBOL] [TARGET_DELTA] [COUNT]

    # Upload upcoming Friday to the CSP tab (default)
    python3 upload_to_sheet.py TSLA -0.18 4

    # Upload following Friday
    python3 upload_to_sheet.py TSLA -0.18 4 --skip 1

    # Both expirations stacked in the same CSP tab
    python3 upload_to_sheet.py TSLA -0.18 4 --both

    # Specific expiration date
    python3 upload_to_sheet.py AAPL -0.25 3 --date 2026-09-18

    # Custom tab name
    python3 upload_to_sheet.py TSLA -0.18 4 --both --tab CSP

    # Custom spreadsheet ID
    python3 upload_to_sheet.py TSLA -0.18 4 --spreadsheet-id "1ABC...xyz"
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Google Sheets setup
# ---------------------------------------------------------------------------
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SECRETS_DIR = Path(__file__).resolve().parent / 'secrets'
load_dotenv(_SECRETS_DIR / '.env')
load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SCRIPT_DIR = Path(__file__).resolve().parent
FIND_SCRIPT = SCRIPT_DIR / 'find_near_delta_puts.py'

def _env(name, default=''):
    """Read env var and strip surrounding quotes if present."""
    val = os.environ.get(name, default)
    if val is None:
        return default
    return str(val).strip().strip('"').strip("'")


# Default spreadsheet ID (override via env or CLI)
DEFAULT_SPREADSHEET_ID = _env('GOOGLE_SHEET_ID') or _env('GSHEET_ID')
DEFAULT_TAB_NAME = _env('GSHEET_TAB_NAME', 'CSP')

def _resolve_credentials_path():
    """Resolve service-account JSON path from GSHEET_ACCESS_KEY or defaults."""
    raw = (os.environ.get('GSHEET_ACCESS_KEY') or os.environ.get('GOOGLE_CREDENTIALS_PATH') or '').strip().strip('"').strip("'")
    candidates = []
    if raw:
        p = Path(raw)
        if p.is_absolute():
            candidates.append(p)
        else:
            # filename only, secrets/filename, or project-relative path
            candidates.append(SCRIPT_DIR / raw)
            candidates.append(_SECRETS_DIR / raw)
            candidates.append(_SECRETS_DIR / p.name)
            candidates.append(p)
    candidates.append(_SECRETS_DIR / 'google-credentials.json')
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0] if candidates else _SECRETS_DIR / 'google-credentials.json')


DEFAULT_CREDENTIALS_PATH = _resolve_credentials_path()


def next_friday(skip=0):
    """Return the date of the Nth Friday from today."""
    today = datetime.now()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        target = today
    else:
        target = today + timedelta(days=days_until_friday)
    return target + timedelta(weeks=skip)


def run_find_script(symbol, target_delta, count, skip_weeks=0, exp_date=None):
    """Run find_near_delta_puts.py and return its stdout output."""
    cmd = [
        sys.executable, str(FIND_SCRIPT),
        symbol, str(target_delta), str(count),
    ]
    if skip_weeks > 0:
        cmd.extend(['--skip', str(skip_weeks)])
    if exp_date:
        cmd.extend(['--date', exp_date])

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPT_DIR))
    if result.returncode != 0:
        print(f'Error running find_near_delta_puts.py:')
        print(result.stderr)
        sys.exit(1)
    return result.stdout


def parse_table_output(output):
    """Parse the table output from find_near_delta_puts.py into structured data.

    Returns:
        header: list of column names
        rows: list of dicts, one per row
        metadata: dict with underlying, expiration, target_delta
    """
    lines = output.strip().split('\n')

    # Find the header line (contains "Strike", "Delta", etc.)
    header_line_idx = None
    for i, line in enumerate(lines):
        if 'Strike' in line and 'Delta' in line and 'Theta' in line:
            header_line_idx = i
            break

    if header_line_idx is None:
        print('Could not find table header in output.')
        sys.exit(1)

    # Parse header
    header_line = lines[header_line_idx]
    # Extract column names from the header line
    header_pattern = re.compile(
        r'(?P<strike>Strike)\s{2,}'
        r'(?P<delta>Delta)\s{2,}'
        r'(?P<theta>Theta)\s{2,}'
        r'(?P<premium>Premium)\s{2,}'
        r'(?P<expiry>Expiry)\s{2,}'
        r'(?P<symbol>Symbol)'
    )
    header_match = header_pattern.search(header_line)
    if not header_match:
        # Fallback: extract known column names in order
        columns = []
        for name in ['Strike', 'Delta', 'Theta', 'Premium', 'Expiry', 'Symbol']:
            idx = header_line.find(name)
            if idx != -1:
                columns.append(name)
            else:
                columns.append(name.lower())
    else:
        columns = [header_match.group(c) for c in ['strike', 'delta', 'theta', 'premium', 'expiry', 'symbol']]

    # Parse data rows (skip separator line)
    rows = []
    data_start = header_line_idx + 2  # skip header + separator line
    for line in lines[data_start:]:
        line = line.strip()
        if not line:
            continue
        # Parse columns by position
        # Format: "  180.00    -0.1823        0.4521        2.35  26-08-28  TSLA260828P00180000"
        row_match = re.match(
            r'\s*(?P<strike>[\d.]+)\s+'
            r'(?P<delta>-?[\d.]+)\s+'
            r'(?P<theta>-?[\d.]+|n/a)\s+'
            r'(?P<premium>-?[\d.]+|n/a)\s+'
            r'(?P<expiry>\S+)\s+'
            r'(?P<symbol>\S+)',
            line,
        )
        if row_match:
            row = row_match.groupdict()
            rows.append(row)

    # Parse metadata (last few lines)
    metadata = {}
    for line in reversed(lines):
        if line.startswith('Underlying:'):
            m = re.match(r'Underlying:\s+(\S+)\s+@\s+\$([\d.]+)', line)
            if m:
                metadata['underlying'] = m.group(1)
                metadata['spot_price'] = float(m.group(2))
        elif line.startswith('Expiration:'):
            m = re.match(r'Expiration:\s+(.+)', line)
            if m:
                metadata['expiration'] = m.group(1).strip()
        elif line.startswith('Target delta:'):
            m = re.match(r'Target delta:\s+(-?[\d.]+)', line)
            if m:
                metadata['target_delta'] = float(m.group(1))

    return columns, rows, metadata


def get_service_credentials():
    """Load Google Sheets API credentials from service account JSON."""
    cred_path = DEFAULT_CREDENTIALS_PATH

    if not os.path.exists(cred_path):
        print(f'Google credentials file not found at: {cred_path}')
        print()
        print('To set up Google Sheets API access:')
        print('  1. Go to https://console.cloud.google.com/apis/credentials')
        print('  2. Create a service account and download the JSON key')
        print('  3. Save it as secrets/google-credentials.json')
        print('  4. Share the Google Sheet with the service account email')
        print()
        sys.exit(1)

    return service_account.Credentials.from_service_account_file(
        cred_path, scopes=SCOPES
    )


def get_spreadsheet_name(sheets_service, spreadsheet_id):
    """Get the spreadsheet title."""
    sheet = sheets_service.spreadsheets()
    result = sheet.get(spreadsheetId=spreadsheet_id).execute()
    return result.get('properties', {}).get('title', 'Unknown')


def find_or_create_sheet(sheets_service, spreadsheet_id, sheet_name):
    """Find a sheet by name, or create it if it doesn't exist.

    Returns the sheet ID (integer).
    """
    result = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id
    ).execute()
    sheets = result.get('sheets', [])

    for sheet in sheets:
        if sheet['properties']['title'] == sheet_name:
            return sheet['properties']['sheetId']

    # Create new sheet
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            'requests': [{
                'addSheet': {
                    'properties': {
                        'title': sheet_name,
                    }
                }
            }]
        }
    ).execute()

    # Return the new sheet ID
    result = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id
    ).execute()
    for sheet in result.get('sheets', []):
        if sheet['properties']['title'] == sheet_name:
            return sheet['properties']['sheetId']

    return None


def _sheet_range(sheet_name, cell_range=None):
    """Build an A1 range, quoting the sheet name when needed."""
    needs_quotes = any(c in sheet_name for c in " '!") or not sheet_name.isidentifier()
    # Always quote sheet names that contain spaces or special chars
    if needs_quotes or ' ' in sheet_name:
        safe = "'" + sheet_name.replace("'", "''") + "'"
    else:
        safe = sheet_name
    return f'{safe}!{cell_range}' if cell_range else safe


def clear_sheet(sheets_service, spreadsheet_id, sheet_name):
    """Clear all cell content in a specific sheet tab (overwrite, do not append)."""
    sheets_service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=_sheet_range(sheet_name),
        body={},
    ).execute()


def _format_spot(spot):
    if isinstance(spot, (int, float)):
        return f'${spot:.2f}'
    return str(spot) if spot != '' else 'n/a'


def build_section_values(columns, rows, metadata, section_label=None):
    """Build sheet rows for one expiration section."""
    values = []
    underlying = metadata.get('underlying', '')
    spot = metadata.get('spot_price', '')
    expiration = metadata.get('expiration', '')
    target = metadata.get('target_delta', '')

    title = f'{underlying} PUT Options - {expiration}'
    if section_label:
        title = f'{section_label}: {title}'
    values.append([title])
    values.append([
        f'Underlying: {underlying} @ {_format_spot(spot)}  |  '
        f'Expiration: {expiration}  |  Target Delta: {target}'
    ])
    values.append([])
    values.append(columns)
    for row in rows:
        values.append([
            row.get('strike', ''),
            row.get('delta', ''),
            row.get('theta', ''),
            row.get('premium', ''),
            row.get('expiry', ''),
            row.get('symbol', ''),
        ])
    return values


def upload_sections_to_sheet(sheets_service, spreadsheet_id, sheet_name, sections):
    """Overwrite one tab with one or more expiration sections stacked vertically.

    sections: list of dicts with keys columns, rows, metadata, label (optional)
    """
    spreadsheet_title = get_spreadsheet_name(sheets_service, spreadsheet_id)
    print(f'  Spreadsheet: {spreadsheet_title}')
    print(f'  Tab: {sheet_name}')

    find_or_create_sheet(sheets_service, spreadsheet_id, sheet_name)
    clear_sheet(sheets_service, spreadsheet_id, sheet_name)

    values = []
    total_rows = 0
    for i, section in enumerate(sections):
        if i > 0:
            values.append([])  # blank line between sections
            values.append([])
        section_values = build_section_values(
            section['columns'],
            section['rows'],
            section['metadata'],
            section_label=section.get('label'),
        )
        values.extend(section_values)
        total_rows += len(section['rows'])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=_sheet_range(sheet_name, 'A1'),
        valueInputOption='RAW',
        body={'values': values},
    ).execute()

    print(f'  Uploaded {total_rows} rows ({len(sections)} section(s)) to tab "{sheet_name}"')
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Upload option data to a Google Spreadsheet tab.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s TSLA -0.18 4                  upload upcoming Friday to CSP tab
  %(prog)s TSLA -0.18 4 --skip 1         upload following Friday to CSP tab
  %(prog)s TSLA -0.18 4 --both           both expirations stacked in CSP tab
  %(prog)s AAPL -0.25 3 --date 2026-09-18  upload specific expiration
  %(prog)s AAPL -0.25 3 --both --date 2026-09-18  both base date + 1 week in one tab
        """,
    )
    parser.add_argument('symbol', nargs='?', default='TSLA', help='Stock ticker (default: TSLA)')
    parser.add_argument('target_delta', nargs='?', default=-0.18, type=float, help='Target put delta (default: -0.18)')
    parser.add_argument('count', nargs='?', default=4, type=int, help='Number of results (default: 4)')
    parser.add_argument('-s', '--skip', type=int, default=0, dest='skip_weeks',
                        help='Skip N Fridays ahead (0 = next Friday, 1 = following Friday)')
    parser.add_argument('-d', '--date', type=str, dest='exp_date',
                        help='Exact expiration date in YYYY-MM-DD format')
    parser.add_argument('--both', action='store_true',
                        help='Upload both upcoming and following Friday into the same tab')
    parser.add_argument('--tab', type=str, default=None,
                        help=f'Target tab name (default: {DEFAULT_TAB_NAME})')
    parser.add_argument('--spreadsheet-id', type=str, default=None,
                        help='Google Spreadsheet ID (overrides GOOGLE_SHEET_ID / GSHEET_ID env var)')

    args = parser.parse_args()

    # Validate API credentials
    if not os.environ.get('ALPACA_API_KEY') or not os.environ.get('ALPACA_API_SECRET'):
        parser.error(
            'Alpaca API credentials not set. Ensure ALPACA_API_KEY and ALPACA_API_SECRET '
            'are in secrets/.env or the project .env file.'
        )

    # Validate spreadsheet ID
    spreadsheet_id = args.spreadsheet_id or DEFAULT_SPREADSHEET_ID
    if not spreadsheet_id:
        parser.error(
            'No spreadsheet ID provided. Set GSHEET_ID in .env or use --spreadsheet-id.'
        )

    tab_name = args.tab or DEFAULT_TAB_NAME

    # Determine which expiration fetches to perform
    fetches = []
    if args.both:
        if args.exp_date:
            base_date = datetime.strptime(args.exp_date, '%Y-%m-%d')
            following_date = (base_date + timedelta(weeks=1)).strftime('%Y-%m-%d')
            fetches.append({
                'label': 'Next expiration',
                'exp_date': args.exp_date,
                'skip': 0,
            })
            fetches.append({
                'label': 'Following expiration',
                'exp_date': following_date,
                'skip': 0,
            })
        else:
            fetches.append({
                'label': 'Next Friday',
                'exp_date': None,
                'skip': 0,
            })
            fetches.append({
                'label': 'Following Friday',
                'exp_date': None,
                'skip': 1,
            })
    else:
        fetches.append({
            'label': 'Expiration',
            'exp_date': args.exp_date,
            'skip': args.skip_weeks,
        })

    # Authenticate
    print('Authenticating with Google Sheets API...')
    creds = get_service_credentials()
    sheets_service = build('sheets', 'v4', credentials=creds)

    print(f'Spreadsheet ID: {spreadsheet_id}')
    print(f'Target tab: {tab_name}\n')

    sections = []
    for i, fetch in enumerate(fetches, 1):
        if fetch['exp_date']:
            exp_display = fetch['exp_date']
        else:
            exp_display = next_friday(skip=fetch['skip']).strftime('%Y-%m-%d')
        print(f'--- Fetch {i}/{len(fetches)}: {fetch["label"]} ({exp_display}) ---')

        output = run_find_script(
            symbol=args.symbol,
            target_delta=args.target_delta,
            count=args.count,
            skip_weeks=fetch['skip'],
            exp_date=fetch['exp_date'],
        )
        columns, rows, metadata = parse_table_output(output)

        if not rows:
            print(f'  No data rows found. Skipping.\n')
            continue

        print(f'  Found {len(rows)} options (expiration {metadata.get("expiration", exp_display)})')
        sections.append({
            'label': fetch['label'],
            'columns': columns,
            'rows': rows,
            'metadata': metadata,
        })
        print()

    if not sections:
        print('No data to upload.')
        sys.exit(1)

    upload_sections_to_sheet(sheets_service, spreadsheet_id, tab_name, sections)
    print('\nUpload complete.')


if __name__ == '__main__':
    main()