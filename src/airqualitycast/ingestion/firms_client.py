"""NASA FIRMS VIIRS active-fire detections (CSV API)."""
from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from airqualitycast.config import get_logger

log = get_logger(__name__)

_BASE = "https://firms.modaps.eosdis.nasa.gov/api"


class FIRMSClient:
    def __init__(self, map_key: str, timeout_s: float = 30.0) -> None:
        if not map_key:
            raise ValueError("FIRMS map_key is required")
        self._map_key = map_key
        self._timeout = timeout_s

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    )
    def _fetch_csv(self, url: str) -> str:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text

    def fetch_fires_for_india(self, days: int = 1) -> pd.DataFrame:
        """Fetch the last `days` (1-10) of VIIRS_SNPP_NRT detections for India."""
        days = max(1, min(10, days))
        url = f"{_BASE}/country/csv/{self._map_key}/VIIRS_SNPP_NRT/IND/{days}"
        try:
            text = self._fetch_csv(url)
        except httpx.HTTPError as exc:
            log.error("firms.fetch_failed", error=str(exc))
            return pd.DataFrame()

        if not text or text.lstrip().startswith("Invalid") or "<html" in text[:200].lower():
            log.warning("firms.empty_or_invalid_response")
            return pd.DataFrame()

        df = pd.read_csv(StringIO(text))
        if df.empty:
            return df

        df.columns = [c.strip().lower() for c in df.columns]
        df = _normalize_firms(df)
        return df


def _normalize_firms(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise FIRMS columns and construct a deterministic fire_id."""
    rename = {
        "bright_ti4": "brightness",
        "bright_ti5": "brightness_t5",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "acq_date" in df.columns and "acq_time" in df.columns:
        df["detected_at"] = pd.to_datetime(
            df["acq_date"].astype(str) + " " + df["acq_time"].astype(str).str.zfill(4),
            format="%Y-%m-%d %H%M",
            utc=True,
            errors="coerce",
        )
    else:
        df["detected_at"] = datetime.now(tz=timezone.utc)

    sat_col = df.get("satellite", pd.Series(["VIIRS_SNPP"] * len(df)))
    df["fire_id"] = (
        sat_col.astype(str)
        + "_"
        + df["acq_date"].astype(str)
        + "_"
        + df["acq_time"].astype(str).str.zfill(4)
        + "_"
        + df["latitude"].round(4).astype(str)
        + "_"
        + df["longitude"].round(4).astype(str)
    )
    return df
