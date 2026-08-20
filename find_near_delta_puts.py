#!/usr/bin/env python3
"""
Find put options with delta closest to a target for a given expiration date.
Uses Alpaca v1beta1/options/snapshots endpoint (same API as test_straddle.php).

Usage:
    python3 find_near_delta_puts.py [SYMBOL] [TARGET_DELTA] [COUNT]
    python3 find_near_delta_puts.py TSLA -0.18 4 -s 1
    python3 find_near_delta_puts.py AAPL -0.25 3 --date 2026-09-18
    python3 find_near_delta_puts.py TSLA -0.18 4 --skip 2
    python3 find_near_delta_puts.py TSLA -0.18 4 -d 2026-12-18

Examples:
    python3 find_near_delta_puts.py TSLA -0.18 4
    python3 find_near_delta_puts.py TSLA -0.18 4 -s 1        # next Friday after the immediate next
    python3 find_near_delta_puts.py AAPL -0.25 3 -d 2026-09-18  # specific monthly expiration
"""

import argparse
import os
import requests
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

_SECRETS_DIR = Path(__file__).resolve().parent / 'secrets'
load_dotenv(_SECRETS_DIR / '.env')
load_dotenv()  # fallback: project-root .env

API_KEY = os.environ.get('ALPACA_API_KEY', '')
API_SECRET = os.environ.get('ALPACA_API_SECRET', '')
BASE_URL = 'https://data.alpaca.markets/v1beta1/options/snapshots'


def get_stock_price(symbol):
    resp = requests.get(
        f'https://data.alpaca.markets/v2/stocks/trades/latest?symbols={symbol}',
        headers={
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': API_SECRET,
            'accept': 'application/json',
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data['trades'][symbol]['p']


def next_friday(skip=0):
    today = datetime.now()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        # today is Friday
        target = today
    else:
        target = today + timedelta(days=days_until_friday)
    return target + timedelta(weeks=skip)


def format_option_symbol(symbol_str):
    """Parse an Alpaca option symbol into components.
    Format: TSLA + YYMMDD + C/P + 8-digit strike = 4 + 6 + 1 + 8 = 19 chars
    """
    raw = symbol_str
    underlying = raw[:-15]
    expiration = raw[-15:-9]
    option_type = raw[-9:-8]
    strike_raw = raw[-8:]
    strike = int(strike_raw) / 1000
    return underlying, expiration, option_type, strike


def fetch_puts_with_greeks(symbol, exp_date, spot_price):
    """
    Fetch put option snapshots for the given expiration and return
    only those that have greeks data.
    The indicative feed returns greeks for ~18 actively traded strikes.
    """
    all_with_greeks = []

    resp = requests.get(
        f'{BASE_URL}/{symbol}',
        params={
            'feed': 'indicative',
            'type': 'put',
            'limit': '100',
            'expiration_date': exp_date,
        },
        headers={
            'APCA-API-KEY-ID': API_KEY,
            'APCA-API-SECRET-KEY': API_SECRET,
            'accept': 'application/json',
        },
    )
    if resp.status_code != 200:
        return all_with_greeks

    data = resp.json()
    puts = data.get('snapshots', {})

    expected_exp = exp_date[2:10].replace('-', '')

    for sym, snap in puts.items():
        # Format: TSLA + YYMMDD + C/P + 8-digit strike
        if len(sym) < 19:
            continue
        # Check it's a put (P at position -9)
        if sym[-9:-8] != 'P':
            continue

        exp_in_symbol = sym[-15:-9]
        if exp_in_symbol != expected_exp:
            continue

        greeks = snap.get('greeks', {})
        delta = greeks.get('delta')
        if delta is not None:
            all_with_greeks.append((sym, snap, delta))

    return all_with_greeks


def main():
    parser = argparse.ArgumentParser(
        description='Find PUT options with delta closest to a target value.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s TSLA -0.18 4            next Friday, target delta -0.18, 4 results
  %(prog)s TSLA -0.18 4 -s 1       skip 1 Friday (2nd Friday out)
  %(prog)s TSLA -0.18 4 --skip 2   skip 2 Fridays (3rd Friday out)
  %(prog)s AAPL -0.25 3 -d 2026-09-18  specific monthly expiration
  %(prog)s AAPL -0.25 3 --date 2026-12-18 quarterly expiration
        """,
    )
    parser.add_argument('symbol', nargs='?', default='TSLA', help='Stock ticker (default: TSLA)')
    parser.add_argument('target_delta', nargs='?', default=-0.18, type=float, help='Target put delta (default: -0.18)')
    parser.add_argument('count', nargs='?', default=4, type=int, help='Number of results (default: 4)')
    parser.add_argument('-s', '--skip', type=int, default=0, dest='skip_weeks',
                        help='Skip N Fridays ahead (0 = next Friday, 1 = following Friday, etc.)')
    parser.add_argument('-d', '--date', type=str, dest='exp_date',
                        help='Exact expiration date in YYYY-MM-DD format')

    args = parser.parse_args()

    # Validate API credentials
    if not API_KEY or not API_SECRET:
        parser.error(
            'API credentials not set. Copy .env.example to secrets/.env '
            'and fill in your Alpaca API key and secret.'
        )

    # Validate: --skip and --date are mutually exclusive
    if args.skip_weeks > 0 and args.exp_date:
        parser.error('Cannot specify both --skip and --date.')

    symbol = args.symbol
    target_delta = args.target_delta
    count = args.count

    # Resolve expiration date
    if args.exp_date:
        try:
            exp_date = datetime.strptime(args.exp_date, '%Y-%m-%d')
        except ValueError:
            parser.error(f'Invalid date format: {args.exp_date}. Use YYYY-MM-DD.')
    else:
        exp_date = next_friday(skip=args.skip_weeks)

    exp_formatted = exp_date.strftime('%Y-%m-%d')
    exp_ymd = exp_date.strftime('%y%m%d')

    print(f'Fetching {symbol} spot price...')
    price = get_stock_price(symbol)
    print(f'{symbol} spot: ${price:.2f}\n')

    print(f'Expiration date: {exp_formatted} ({exp_ymd})')
    print(f'Finding {count} PUT options with delta closest to {target_delta}\n')

    puts_with_greeks = fetch_puts_with_greeks(symbol, exp_formatted, price)

    if not puts_with_greeks:
        print('No put options with greeks data found for this expiration.')
        sys.exit(1)

    # Sort by absolute distance from target delta
    puts_with_greeks.sort(key=lambda x: abs(x[2] - target_delta))
    closest = puts_with_greeks[:count]
    total_available = len(puts_with_greeks)

    if len(closest) < count:
        print(f'(Only {len(closest)} of {count} requested have greeks data out of {total_available} total)\n')
    else:
        print(f'(Found {len(closest)} of {total_available} available with greeks data)\n')

    # Print table
    print(f'{"Strike":>10}  {"Delta":>8}  {"Theta":>10}  {"Premium":>10}  {"Expiry":>12}  {"Symbol"}')
    print('-' * 72)

    for sym, snap, delta in closest:
        _, exp_raw, _, strike = format_option_symbol(sym)
        greeks = snap.get('greeks', {})
        theta = greeks.get('theta', 'n/a')
        premium = snap.get('dailyBar', {}).get('c', 'n/a')

        delta_str = f'{delta:.4f}'
        theta_str = f'{theta:.4f}' if isinstance(theta, (int, float)) else 'n/a'
        premium_str = f'{premium:.2f}' if isinstance(premium, (int, float)) else 'n/a'
        exp_display = f'{exp_raw[:2]}-{exp_raw[2:4]}-{exp_raw[4:6]}'

        print(f'{strike:>10.2f}  {delta_str:>8}  {theta_str:>10}  {premium_str:>10}  {exp_display:>12}  {sym}')

    print(f'\nUnderlying: {symbol} @ ${price:.2f}')
    print(f'Expiration: {exp_formatted}')
    print(f'Target delta: {target_delta}')


if __name__ == '__main__':
    main()