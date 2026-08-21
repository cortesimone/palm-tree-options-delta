#!/usr/bin/env python3
"""
Calculate ATM (At-The-Money) straddle prices for upcoming option expirations.

Detects expiration cadence for the ticker:
  - multiple expirations per week  -> next 5 expirations
  - weekly (or less frequent)      -> next 3 expirations

For each selected expiration, the ATM straddle is the sum of the ATM call
and ATM put midpoint prices ((bid + ask) / 2).

Usage:
    python3 atm_straddle.py SYMBOL
    python3 atm_straddle.py TSLA
    python3 atm_straddle.py AAPL
"""

import argparse
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

import requests

from config import config
from utils.expiration import is_today_an_expiration


def _headers():
    return config.alpaca_headers


def get_stock_price(symbol):
    resp = requests.get(
        f'{config.data_base}/v2/stocks/trades/latest',
        params={'symbols': symbol},
        headers=_headers(),
        timeout=config.api_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    trades = data.get('trades') or {}
    if symbol not in trades:
        raise KeyError(symbol)
    return trades[symbol]['p']


def get_available_expirations(symbol, look_ahead_days=120):
    """
    Return sorted unique expiration dates (YYYY-MM-DD) for active option
    contracts on the underlying, using the trading API contracts endpoint.
    """
    today = datetime.now().date()
    end = today + timedelta(days=look_ahead_days)
    expirations = set()
    page_token = None

    while True:
        params = {
            'underlying_symbols': symbol,
            'status': 'active',
            'limit': 1000,
            'expiration_date_gte': today.isoformat(),
            'expiration_date_lte': end.isoformat(),
        }
        if page_token:
            params['page_token'] = page_token

        resp = requests.get(config.contracts_url, params=params, headers=_headers(), timeout=60)
        resp.raise_for_status()
        data = resp.json()
        contracts = data.get('option_contracts') or []

        if not contracts and not expirations and page_token is None:
            return []

        for c in contracts:
            exp = c.get('expiration_date')
            if exp:
                expirations.add(exp)

        page_token = data.get('next_page_token')
        if not page_token:
            break
        time.sleep(config.api_delay)

    return sorted(expirations)


def has_multiple_expirations_per_week(expirations):
    """True if any ISO calendar week contains 2+ expiration dates."""
    by_week = defaultdict(int)
    for exp in expirations:
        d = datetime.strptime(exp, '%Y-%m-%d').date()
        iso = d.isocalendar()
        by_week[(iso[0], iso[1])] += 1
    return any(count >= 2 for count in by_week.values())


def find_atm_contracts(symbol, exp_date, spot_price):
    """
    Return (call_symbol, put_symbol, strike) for the strike closest to spot
    on the given expiration, or None if unavailable.
    """
    resp = requests.get(
        config.contracts_url,
        params={
            'underlying_symbols': symbol,
            'status': 'active',
            'expiration_date': exp_date,
            'limit': 1000,
        },
        headers=_headers(),
        timeout=60,
    )
    resp.raise_for_status()
    contracts = resp.json().get('option_contracts') or []
    if not contracts:
        return None

    calls = [c for c in contracts if c.get('type') == 'call']
    puts = [c for c in contracts if c.get('type') == 'put']
    if not calls or not puts:
        return None

    best_call = min(calls, key=lambda c: abs(float(c['strike_price']) - spot_price))
    strike = float(best_call['strike_price'])
    same_strike_puts = [p for p in puts if abs(float(p['strike_price']) - strike) < 1e-6]
    if same_strike_puts:
        best_put = same_strike_puts[0]
    else:
        best_put = min(puts, key=lambda p: abs(float(p['strike_price']) - spot_price))
        strike = float(best_put['strike_price'])

    return best_call['symbol'], best_put['symbol'], strike


def _midpoint_from_snapshot(snap):
    """Prefer latestQuote mid; fall back to latestTrade / dailyBar close."""
    quote = snap.get('latestQuote') or {}
    bid = quote.get('bp')
    ask = quote.get('ap')
    if bid is not None and ask is not None and bid >= 0 and ask > 0:
        return (float(bid) + float(ask)) / 2.0

    trade = snap.get('latestTrade') or {}
    if trade.get('p') is not None:
        return float(trade['p'])

    bar = snap.get('dailyBar') or {}
    if bar.get('c') is not None:
        return float(bar['c'])

    return None


def get_option_midpoints(option_symbols):
    """Fetch snapshots for specific option symbols; return {symbol: mid}."""
    last_err = None
    for attempt in range(4):
        resp = requests.get(
            config.snapshots_url,
            params={
                'symbols': ','.join(option_symbols),
                'feed': 'indicative',
            },
            headers=_headers(),
            timeout=config.api_timeout,
        )
        if resp.status_code == 429:
            last_err = resp
            time.sleep(1.5 * (attempt + 1))
            continue
        resp.raise_for_status()
        snapshots = resp.json().get('snapshots') or {}
        out = {}
        for sym in option_symbols:
            snap = snapshots.get(sym)
            if snap:
                mid = _midpoint_from_snapshot(snap)
                if mid is not None:
                    out[sym] = mid
        return out
    if last_err is not None:
        last_err.raise_for_status()
    return {}


def get_atm_straddle(symbol, exp_date, spot_price):
    """
    Calculate ATM straddle for one expiration.
    Returns dict with strike, call_mid, put_mid, straddle -- or None.
    """
    pair = find_atm_contracts(symbol, exp_date, spot_price)
    if not pair:
        return None

    call_sym, put_sym, strike = pair
    mids = get_option_midpoints([call_sym, put_sym])
    call_mid = mids.get(call_sym)
    put_mid = mids.get(put_sym)
    if call_mid is None or put_mid is None:
        return None

    return {
        'strike': strike,
        'call': call_mid,
        'put': put_mid,
        'straddle': call_mid + put_mid,
        'call_symbol': call_sym,
        'put_symbol': put_sym,
    }


def main():
    config.require_api_credentials()

    parser = argparse.ArgumentParser(
        description='Calculate ATM straddle prices for upcoming option expirations.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s TSLA
  %(prog)s AAPL
        """,
    )
    parser.add_argument('symbol', help='Stock ticker symbol')
    args = parser.parse_args()
    symbol = args.symbol.upper().strip()

    try:
        spot_price = get_stock_price(symbol)
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status == 404:
            print(f'Error: Ticker "{symbol}" not found.')
        else:
            print(f'Error fetching stock price: {e}')
        sys.exit(1)
    except KeyError:
        print(f'Error: Ticker "{symbol}" not found.')
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f'Error: Failed to fetch stock price: {e}')
        sys.exit(1)

    print(f'{symbol} Spot Price: ${spot_price:.2f}\n')

    try:
        expirations = get_available_expirations(symbol)
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status in (404, 422):
            print(f'Error: No options data found for ticker "{symbol}".')
        else:
            print(f'Error fetching option expirations: {e}')
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f'Error: Failed to fetch option expirations: {e}')
        sys.exit(1)

    if not expirations:
        print(f'Error: No active option expirations found for "{symbol}".')
        sys.exit(1)

    multi_per_week = has_multiple_expirations_per_week(expirations)
    num_expirations = 5 if multi_per_week else 3
    cadence = 'multiple expirations per week' if multi_per_week else 'weekly expirations'

    # Skip today's expiration — data collection starts from the next available date
    today_str = datetime.now().date().isoformat()
    expirations = [e for e in expirations if e > today_str]

    if not expirations:
        print(f'Error: No future option expirations found for "{symbol}".')
        sys.exit(1)

    selected = expirations[:num_expirations]

    print(f'Cadence: {cadence} -> showing next {num_expirations} expiration(s)\n')
    print(
        f'{"Expiration":>12}  {"DTE":>5}  {"ATM Strike":>11}  '
        f'{"Call":>8}  {"Put":>8}  {"Straddle":>10}'
    )
    print('-' * 66)

    today = datetime.now().date()
    for exp in selected:
        exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
        dte = (exp_date - today).days

        try:
            result = get_atm_straddle(symbol, exp, spot_price)
            time.sleep(0.2)
        except requests.exceptions.RequestException as e:
            print(f'{exp:>12}  {dte:>5}  {"-":>11}  {"-":>8}  {"-":>8}  error: {e}')
            continue

        if result is None:
            print(f'{exp:>12}  {dte:>5}  {"N/A":>11}  {"N/A":>8}  {"N/A":>8}  {"N/A":>10}')
            continue

        print(
            f'{exp:>12}  {dte:>5}  {result["strike"]:>11.2f}  '
            f'{result["call"]:>8.2f}  {result["put"]:>8.2f}  '
            f'{result["straddle"]:>10.2f}'
        )

    print()
    print(f'Underlying: {symbol} @ ${spot_price:.2f}')
    print(f'Straddle = ATM call mid + ATM put mid  (latestQuote bid/ask)')


if __name__ == '__main__':
    main()