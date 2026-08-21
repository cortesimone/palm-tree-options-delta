import json
import os
from pathlib import Path

from dotenv import load_dotenv


_ROOT = Path(__file__).resolve().parent.parent
_SECRETS = _ROOT / 'secrets'
_CONFIG = _ROOT / 'config'


def _strip(val):
    if val is None:
        return ''
    return str(val).strip().strip('"').strip("'")


def _resolve_env():
    return os.environ.get('APP_ENV', 'local').strip().lower()


def _load_json(path):
    if path.is_file():
        with open(path) as f:
            return json.load(f)
    return {}


class AppConfig:
    """
    Hierarchical config loader with 3 tiers (highest priority first):

      1. OS environment variables          (e.g. ALPACA_API_KEY=... in shell)
      2. .env.<APP_ENV> file               (e.g. .env.production)
      3. config/defaults.json              (committed, non-secret base values)

    Secret files in secrets/.env are always loaded as a fourth (lowest) tier
    for backward compatibility with existing deployments.

    Usage:
        from config import config
        print(config.alpaca_api_key)
        print(config.is_production)
    """

    def __init__(self):
        self._env = _resolve_env()
        self._defaults = _load_json(_CONFIG / 'defaults.json')
        self._env_overrides = self._load_env_file(_ROOT / f'.env.{self._env}')
        self._secrets = self._load_env_file(_SECRETS / '.env')
        self._project_env = self._load_env_file(_ROOT / '.env')

        # Pre-resolve all values so attribute access is fast and clean.
        self._values = {}
        self._merge(self._defaults, self._project_env, self._env_overrides, self._secrets)
        self._merge_from_osenv()

        # Derived / computed properties
        self._api_key = _strip(self._values.get('ALPACA_API_KEY', ''))
        self._api_secret = _strip(self._values.get('ALPACA_API_SECRET', ''))
        self._gsheet_access_key = _strip(self._values.get('GSHEET_ACCESS_KEY', ''))
        self._gsheet_id = _strip(self._values.get('GSHEET_ID') or self._values.get('GOOGLE_SHEET_ID', ''))
        self._gsheet_tab = _strip(self._values.get('GSHEET_TAB_NAME', 'CSP'))
        self._is_production = self._env == 'production'
        self._is_local = self._env == 'local'

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_env_file(path):
        """Parse a .env file into a dict without side-effects (no os.environ)."""
        result = {}
        if not path.is_file():
            return result
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, _, value = line.partition('=')
                result[key.strip()] = _strip(value)
        return result

    def _merge(self, *dicts):
        for d in dicts:
            self._values.update(d)

    def _merge_from_osenv(self):
        """OS env vars always win -- loaded last so they override file values."""
        for key in ('ALPACA_API_KEY', 'ALPACA_API_SECRET',
                     'GSHEET_ACCESS_KEY', 'GSHEET_ID', 'GOOGLE_SHEET_ID',
                     'GSHEET_TAB_NAME'):
            val = os.environ.get(key)
            if val is not None:
                self._values[key] = val

    # ------------------------------------------------------------------
    # Public attributes
    # ------------------------------------------------------------------

    @property
    def env(self):
        """Current environment: 'local' or 'production'."""
        return self._env

    @property
    def is_production(self):
        return self._is_production

    @property
    def is_local(self):
        return self._is_local

    @property
    def alpaca_api_key(self):
        return self._api_key

    @property
    def alpaca_api_secret(self):
        return self._api_secret

    @property
    def gsheet_access_key(self):
        return self._gsheet_access_key

    @property
    def gsheet_id(self):
        return self._gsheet_id

    @property
    def gsheet_tab_name(self):
        return self._gsheet_tab

    @property
    def data_base(self):
        return 'https://data.alpaca.markets'

    @property
    def trade_base(self):
        return 'https://paper-api.alpaca.markets'

    @property
    def contracts_url(self):
        return f'{self.trade_base}/v2/options/contracts'

    @property
    def snapshots_url(self):
        return f'{self.data_base}/v1beta1/options/snapshots'

    @property
    def secrets_dir(self):
        return _SECRETS

    @property
    def api_delay(self):
        """Delay between API calls to respect rate limits (seconds)."""
        return float(os.environ.get('API_DELAY', '0.15'))

    @property
    def api_timeout(self):
        """HTTP request timeout (seconds)."""
        return int(os.environ.get('API_TIMEOUT', '30'))

    @property
    def cron_symbol(self):
        """Default ticker symbol for cron uploads."""
        return os.environ.get('CRON_SYMBOL', 'SPCX')

    @property
    def cron_target_delta(self):
        """Target delta for cron put-finding."""
        return os.environ.get('CRON_TARGET_DELTA', '-0.18')

    @property
    def cron_count(self):
        """Number of results for cron uploads."""
        return os.environ.get('CRON_COUNT', '4')

    @property
    def cron_use_both(self):
        """Whether cron uploads both upcoming and following Friday."""
        val = os.environ.get('CRON_USE_BOTH', 'False')
        return val.lower() in ('true', '1', 'yes')

    @property
    def alpaca_headers(self):
        return {
            'APCA-API-KEY-ID': self._api_key,
            'APCA-API-SECRET-KEY': self._api_secret,
            'accept': 'application/json',
        }

    # ------------------------------------------------------------------
    # GSheet credentials path resolution
    # ------------------------------------------------------------------

    def resolve_gsheet_credentials_path(self):
        raw = _strip(self._gsheet_access_key) or \
              _strip(os.environ.get('GOOGLE_CREDENTIALS_PATH', ''))
        candidates = []
        if raw:
            p = Path(raw)
            if p.is_absolute():
                candidates.append(p)
            else:
                candidates.append(_ROOT / raw)
                candidates.append(_SECRETS / raw)
                candidates.append(_SECRETS / p.name)
                candidates.append(p)
        candidates.append(_SECRETS / 'google-credentials.json')
        for c in candidates:
            if c.exists():
                return str(c)
        return str(candidates[0])

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def require_api_credentials(self):
        if not self._api_key or not self._api_secret:
            raise RuntimeError(
                'Alpaca API credentials not set. '
                f'APP_ENV={self._env}\n'
                'Set ALPACA_API_KEY and ALPACA_API_SECRET in your '
                f'.env.{self._env}, secrets/.env, or as OS environment variables.'
            )

    def require_gsheet_id(self):
        if not self._gsheet_id:
            raise RuntimeError(
                'Google Sheet ID not set. '
                f'APP_ENV={self._env}\n'
                'Set GSHEET_ID or GOOGLE_SHEET_ID in your '
                f'.env.{self._env}, secrets/.env, or as an OS environment variable.'
            )