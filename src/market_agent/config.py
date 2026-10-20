import os
from pathlib import Path

from dotenv import load_dotenv


def _home() -> Path:
    """Where .env, data/ and reports/ live.

    MARKET_AGENT_HOME wins; otherwise the source checkout when running from it,
    or the current directory when the package is installed into another project.
    """
    if home := os.environ.get("MARKET_AGENT_HOME"):
        return Path(home).expanduser().resolve()
    source_root = Path(__file__).resolve().parents[2]
    return source_root if (source_root / "pyproject.toml").exists() else Path.cwd()


ROOT = _home()
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
DB_PATH = Path(os.environ.get("MARKET_AGENT_DB", DATA_DIR / "market.duckdb"))

load_dotenv(ROOT / ".env")

# kind: "yield" -> compare as change in basis points; "level" -> compare as percent change
FRED_SERIES = {
    "DGS3MO": ("3-Month Treasury yield (%)", "yield"),
    "DGS2": ("2-Year Treasury yield (%)", "yield"),
    "DGS10": ("10-Year Treasury yield (%)", "yield"),
    "DGS30": ("30-Year Treasury yield (%)", "yield"),
    "T10Y2Y": ("10Y minus 2Y spread (%)", "yield"),
    "DFII10": ("10-Year TIPS real yield (%)", "yield"),
    "DEXJPUS": ("USD/JPY, noon NY buying rate (weekly release)", "level"),
    "DTWEXBGS": ("Nominal broad US dollar index", "level"),
    "VIXCLS": ("CBOE VIX close", "level"),
}

DEFAULT_HISTORY_START = "2020-01-01"

# AI-led vs broad/defensive market, compared as equal-weight ETF baskets
ROTATION_AI = ["SMH", "QQQ"]
ROTATION_NON_AI = ["RSP", "IWM", "XLV", "XLP", "XLU"]


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value
