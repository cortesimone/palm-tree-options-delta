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
import requests
import sys
from datetime import datetime, timedelta

from config import config
from utils.expiration import next_friday_skip_today, is_today_an_expiration, next_available_expiration


def get_stock_price(symbol):
    resp = requests.get(
        f'{config.data_base}/v2/stocks/trades/latest?symbols={symbol}',
        headers=config.alpaca_headers,
        timeout=config.api_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data['trades'][symbol]['p']


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


def _estimate_delta(strike, spot_price, days_to_exp):
    """Estimate put delta when greeks are unavailable (e.g. 0DTE on indicative feed).

    Uses a normal-CDF approximation based on moneyness.
    """
    if days_to_exp <= 0:
        # At expiration: delta is 1.0 if ITM, 0.0 if OTM
        if strike > spot_price:
            return -1.0
        elif strike == spot_price:
            return -0.5
        else:
            return 0.0

    log_moneyness = (spot_price - strike) / spot_price
    # Rough approximation: map moneyness to delta via sigmoid-like curve
    # ATM (log_moneyness ≈ 0) → delta ≈ -0.5
    # Deep ITM (log_moneyness > 0.1) → delta ≈ -1.0
    # Deep OTM (log_moneyness < -0.1) → delta ≈ 0.0
    import math
    x = log_moneyness * 15.0  # steepness factor
    sigmoid = 1.0 / (1.0 + math.exp(x))
    return -sigmoid


def fetch_puts_with_greeks(symbol, exp_date, spot_price):
    """
    Fetch put option snapshots for the given expiration and return
    only those that have greeks data (or estimated delta if greeks are missing).

    Returns:
        results: list of (symbol, snapshot, delta, has_real_greeks)
        has_real_greeks_any: True if at least one option had real greeks

    The indicative feed returns greeks for ~18 actively traded strikes on
    normal days, but may return zero greeks for 0DTE options. In that case
    we fall back to estimating delta from moneyness so the script still
    produces results.
    """
    all_with_greeks = []

    page_token = None
    while True:
        params = {
            'feed': 'indicative',
            'type': 'put',
            'limit': '100',
            'expiration_date': exp_date,
        }
        if page_token:
            params['page_token'] = page_token

        resp = requests.get(
            f'{config.data_base}/v1beta1/options/snapshots/{symbol}',
            params=params,
            headers=config.alpaca_headers,
            timeout=config.api_timeout,
        )
        if resp.status_code != 200:
            break

        data = resp.json()
        puts = data.get('snapshots', {})

        expected_exp = exp_date[2:10].replace('-', '')

        for sym, snap in puts.items():
            if len(sym) < 19:
                continue
            if sym[-9:-8] != 'P':
                continue

            exp_in_symbol = sym[-15:-9]
            if exp_in_symbol != expected_exp:
                continue

            greeks = snap.get('greeks', {})
            delta = greeks.get('delta')
            if delta is not None:
                all_with_greeks.append((sym, snap, delta, True))
            else:
                # Fall back: estimate delta from moneyness
                # Calculate days to expiration
                try:
                    exp_parts = exp_in_symbol
                    exp_str = f'{exp_parts[:2]}-{exp_parts[2:4]}-{exp_parts[4:6]}'
                    exp_dt = datetime.strptime(exp_str, '%y-%m-%d')
                    days_to_exp = (exp_dt - datetime.now()).total_seconds() / 86400
                except (ValueError, TypeError):
                    days_to_exp = 0

                est_delta = _estimate_delta(float(sym[-8:]) / 1000, spot_price, days_to_exp)
                all_with_greeks.append((sym, snap, est_delta, False))

        page_token = data.get('next_page_token')
        if not page_token:
            break

    has_real = any(r[3] for r in all_with_greeks)
    return all_with_greeks, has_real


def main():
    config.require_api_credentials()

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
        exp_date = next_friday_skip_today(skip=args.skip_weeks)

    exp_formatted = exp_date.strftime('%Y-%m-%d')
    exp_ymd = exp_date.strftime('%y%m%d')

    # If the resolved date is today, skip to next available Friday
    if is_today_an_expiration(exp_formatted):
        print(f'  Today ({exp_formatted}) is an expiration date — skipping to next available.\n')
        exp_date = exp_date + timedelta(weeks=1)
        exp_formatted = exp_date.strftime('%Y-%m-%d')
        exp_ymd = exp_date.strftime('%y%m%d')

    print(f'Fetching {symbol} spot price...')
    price = get_stock_price(symbol)
    print(f'{symbol} spot: ${price:.2f}\n')

    print(f'Expiration date: {exp_formatted} ({exp_ymd})')
    print(f'Finding {count} PUT options with delta closest to {target_delta}\n')

    puts_with_greeks, has_real_greeks = fetch_puts_with_greeks(symbol, exp_formatted, price)

    if not puts_with_greeks:
        print('No put options with greeks data found for this expiration.')
        sys.exit(1)

    # Sort: use real delta distance when greeks available, otherwise sort by
    # premium ascending (cheapest = most OTM = delta closest to 0).
    if has_real_greeks:
        puts_with_greeks.sort(key=lambda x: abs(x[2] - target_delta))
        note = f'(Found {len(puts_with_greeks)} of {len(puts_with_greeks)} available with greeks data)'
    else:
        # No real greeks (e.g. 0DTE on indicative feed). Sort by premium
        # ascending so the most OTM (cheapest) options come first.
        puts_with_greeks.sort(key=lambda x: (x[1].get('dailyBar', {}).get('c', float('inf'))))
        note = f'(No greeks available; sorted by premium ascending — most OTM first out of {len(puts_with_greeks)} total)'

    closest = puts_with_greeks[:count]

    if len(closest) < count:
        print(f'(Only {len(closest)} of {count} requested)')
    print(f'{note}\n')

    # Print table
    print(f'{"Strike":>10}  {"Delta":>8}  {"Theta":>10}  {"Premium":>10}  {"Expiry":>12}  {"Symbol"}')
    print('-' * 72)

    for sym, snap, delta, has_greeks in closest:
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