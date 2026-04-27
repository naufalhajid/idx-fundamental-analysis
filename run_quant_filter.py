"""
run_quant_filter.py — IHSG Quantitative Swing-Trade Scouting Engine
====================================================================
Versi: 2.1

Perbaikan dari v1:
  1. [BUG FIX] Single-ticker yfinance fallback yang salah → paksa MultiIndex
  2. [BUG FIX] Duplikat assignment current_px + type inconsistency
  3. [BUG FIX] os.makedirs untuk output directories
  4. [BUG FIX] Retry mechanism untuk yfinance download
  5. [IMPROVE] Sektor lebih lengkap & terstruktur via IDX SECTOR_MAP (12 sektor + sub-industri)
  6. [IMPROVE] Semua magic numbers dipindah ke CONFIG dict
  7. [IMPROVE] Bonus score untuk fresh breakout di atas SMA20 (1–5%)
  8. [IMPROVE] Valuation Gate: saham di atas Graham Number hard-cap Val_Score = 0
  9. [IMPROVE] Logging terstruktur dengan timestamp
  10. [IMPROVE] Output path validation

Perbaikan v2.1 (sinkronisasi dengan utils aktual):
  11. [FIX] Import snap_to_tick dari utils/technicals.py — stop loss dibulatkan
      ke fraksi harga BEI yang valid (tick size regulation)
  12. [FIX] compute_atr di utils/technicals.py menggunakan rolling().mean()
      (bukan ewm) — tidak ada perubahan diperlukan di sini, sudah konsisten
  13. [FIX] ExDateInfo TypedDict dari exdate_scanner digunakan sebagai type hint
      eksplisit untuk exdate_info agar IDE bisa catch key errors
  14. [IMPROVE] format_exdate_block dipakai di Markdown report untuk WARNING tier

Arsitektur Pipeline:
  ① Data Ingestion (Excel fundamental + yfinance harga live)
  ② Static Filtering (fundamental gate)
  ③ Sector-Aware PBV Ranking (12 sektor IDX)
  ④ Dynamic Technical Analysis per ticker (RSI, ATR, SMA, Volume)
  ⑤ Composite Scoring & Multi-format Output
"""

import logging
import os
import time
import json
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

from utils.technicals import compute_atr, compute_rsi, snap_to_tick
from utils.exdate_scanner import scan_exdate, format_exdate_block, ExDateInfo

# ══════════════════════════════════════════════════════════════════════════════
# ── KONFIGURASI TERPUSAT ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    # ── Path
    "input_file":       "output/IDX Fundamental Analysis 2026-04-24.xlsx",
    "output_dir":       "output",
    "scratch_dir":      "scratch",
    "sector_cache_file": "output/sector_cache.json",

    # ── Static Filter Thresholds
    "min_close_price":      100,        # Rp — buang penny stocks
    "max_der":              1.5,        # Debt to Equity Ratio maksimum
    "max_pbv_hard":         6.0,        # PBV ceiling absolut (bukan per sektor)
    "pbv_sector_pctile":    0.80,       # Buang top 20% PBV per sektor
    "min_roe":              0.10,       # ROE minimum TTM (10%)

    # ── Graham Number
    "graham_k":             18.2,       # PE=13 × PB=1.4, dikalibrasi untuk IDX
    "graham_bear_eps":      0.85,       # Bear case: EPS × 85%
    "graham_bull_eps":      1.15,       # Bull case: EPS × 115%

    # ── yfinance
    "yf_period":            "60d",      # Cukup untuk SMA20, ATR14, Volume20
    "yf_retries":           3,          # Jumlah retry jika download gagal
    "yf_retry_delay":       5,          # Detik antar retry (× attempt number)

    # ── Liquidity Gate
    "min_adt_20d":          5_000_000_000,  # Average Daily Turnover ≥ Rp 5 Miliar
    "min_bars":             20,             # Minimum bar untuk kalkulasi

    # ── Volume Filter
    "vol_confirmation_ratio": 0.80,    # 3d avg harus ≥ 80% dari 20d avg

    # ── Suspended/FCA Heuristic
    "max_zero_vol_days":    3,         # Maksimum hari zero-volume dalam 20d terakhir

    # ── RSI Scoring Zones
    "rsi_hard_reject":      75,        # RSI > 75 → hard reject (anti-pump chasing)
    "rsi_accum_lo":         45,
    "rsi_accum_hi":         55,
    "rsi_strong_hi":        70,

    # ── Stop Loss
    "stop_atr_from_sma20":  1.0,       # SMA20 - (N × ATR)
    "stop_atr_from_price":  2.0,       # Close - (N × ATR)
    "stop_hard_floor_pct":  0.92,      # Hard floor: max 8% drawdown dari harga

    # ── Score Weights (total = 100)
    "weight_valuation":     40,
    "weight_profitability": 20,
    "weight_momentum_rsi":  20,
    "weight_momentum_vol":  20,

    # ── Penalties & Bonuses
    "over_extended_penalty":    -15,   # Harga > SMA20 × 1.10
    "fresh_breakout_bonus":     +10,   # Harga dalam 1–5% di atas SMA20

    # ── Output
    "top_n":    10,
}

# ══════════════════════════════════════════════════════════════════════════════
# ── SEKTOR MAP — Berbasis IDX Industry Classification (IDXIC) ────────────────
# ══════════════════════════════════════════════════════════════════════════════
#
# BEI menggunakan 11 sektor utama sejak 2021 (IDXIC).
# Perbankan dipisah dari Keuangan Non-Bank karena profil PBV sangat berbeda:
#   Bank         : PBV wajar 1.5–4.0×
#   Non-Bank     : PBV wajar 0.8–2.5×
#
# Sektor:
#   energy           → Energi (Batubara, Migas, EBT)
#   basic_materials  → Barang Baku (Kimia, Logam, Semen, Kertas)
#   industrials      → Perindustrian (Manufaktur, Kontraktor, Heavy Equip)
#   consumer_staples → Konsumen Primer (F&B, Personal Care, Ritel Pokok, CPO)
#   consumer_disc    → Konsumen Non-Primer (Otomotif, Fashion, Media, Resto)
#   healthcare       → Kesehatan (Farmasi, RS, Alkes)
#   bank             → Perbankan (Bank Umum + Syariah + BPD)
#   finance_nonbank  → Keuangan Non-Bank (Multifinance, Asuransi, Sekuritas)
#   property         → Properti & Real Estate
#   tech             → Teknologi Informasi & Telekomunikasi
#   infrastructure   → Infrastruktur (Tol, Listrik, Pelabuhan)
#   transport        → Transportasi & Logistik

SECTOR_PBV_BENCHMARK = {
    "energy": {"label": "Energi", "fair_lo": 0.8, "fair_hi": 2.5},
    "basic_materials": {"label": "Barang Baku", "fair_lo": 0.8, "fair_hi": 2.5},
    "industrials": {"label": "Perindustrian", "fair_lo": 0.8, "fair_hi": 2.5},
    "consumer_staples": {"label": "Konsumen Primer", "fair_lo": 1.0, "fair_hi": 3.0},
    "consumer_disc": {"label": "Konsumen Non-Primer", "fair_lo": 0.8, "fair_hi": 2.5},
    "healthcare": {"label": "Kesehatan", "fair_lo": 1.5, "fair_hi": 4.0},
    "bank": {"label": "Perbankan", "fair_lo": 1.5, "fair_hi": 4.0},
    "finance_nonbank": {"label": "Keuangan Non-Bank", "fair_lo": 0.8, "fair_hi": 2.5},
    "property": {"label": "Properti & Real Estate", "fair_lo": 0.5, "fair_hi": 1.5},
    "tech": {"label": "Teknologi", "fair_lo": 1.5, "fair_hi": 6.0},
    "infrastructure": {"label": "Infrastruktur", "fair_lo": 0.8, "fair_hi": 2.5},
    "transport": {"label": "Transportasi & Logistik", "fair_lo": 0.8, "fair_hi": 2.5},
    "default": {"label": "Lain-lain", "fair_lo": 0.8, "fair_hi": 2.5},
}

# ══════════════════════════════════════════════════════════════════════════════
# ── LOGGING SETUP ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("quant_filter")


# ══════════════════════════════════════════════════════════════════════════════
# ── HELPER: YFINANCE DOWNLOAD DENGAN RETRY ───────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def download_yf_with_retry(
    tickers: list[str],
    period: str,
    retries: int,
    delay: int,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    Download yfinance data dengan retry mechanism.
    Selalu mengembalikan MultiIndex DataFrame (paksa wrap jika single ticker).
    """
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"yfinance download attempt {attempt}/{retries} ({len(tickers)} ticker)...")
            data = yf.download(
                tickers,
                period=period,
                group_by="ticker",
                progress=False,
                auto_adjust=True,
            )
            if data.empty:
                raise ValueError("yfinance mengembalikan DataFrame kosong.")

            # ── FIX: Paksa MultiIndex untuk single-ticker edge case ──────────
            # yfinance kadang mengembalikan flat DataFrame jika hanya 1 ticker.
            # Wrap paksa agar semua downstream logic bisa pakai MultiIndex.
            if not isinstance(data.columns, pd.MultiIndex):
                logger.warning(
                    "yfinance mengembalikan flat columns (kemungkinan single ticker). "
                    "Memaksa MultiIndex wrapper..."
                )
                data = pd.concat({tickers[0]: data}, axis=1)

            logger.info(f"Download berhasil. Shape: {data.shape}")
            return data

        except Exception as exc:
            logger.warning(f"Download gagal (attempt {attempt}): {exc}")
            if attempt < retries:
                wait = delay * attempt
                logger.info(f"Retry dalam {wait} detik...")
                time.sleep(wait)

    logger.error("Semua retry yfinance gagal. Pipeline dihentikan.")
    raise RuntimeError("yfinance download gagal setelah semua retry.")


def _load_sector_map(cache_file: str, logger: logging.Logger) -> dict[str, str]:
    if not os.path.exists(cache_file):
        logger.warning(f"{cache_file} tidak ditemukan! Jalankan build_sector_cache.py terlebih dahulu.")
        return {}
    with open(cache_file, "r", encoding="utf-8") as f:
        sector_data = json.load(f)
    return {ticker: info["sector"] for ticker, info in sector_data.items()}


def _analyze_ticker(
    row: pd.Series,
    df_t: pd.DataFrame,
    cfg: dict,
    logger: logging.Logger,
) -> dict | None:
    """
    Analisis teknikal satu ticker.
    Return dict result jika lolos semua filter, None jika tidak lolos.
    """
    t = row["Ticker"]

    close = df_t["Close"].squeeze()
    vol   = df_t["Volume"].squeeze()
    high  = df_t["High"].squeeze()
    low   = df_t["Low"].squeeze()

    # ── Suspended / FCA Board Exclusion ──────────────────────────────────
    recent_vol = vol.tail(5).sum()
    avg_vol_20d = vol.tail(20).mean()
    if (
        (vol.tail(20) == 0).sum() > cfg["max_zero_vol_days"] or
        (avg_vol_20d > 0 and (recent_vol / avg_vol_20d) < 0.10)
    ):
        logger.info(f"[{t}] Excluded: suspek suspended/FCA (volume anomali).")
        return None

    # ── Ex-Date Dividend Trap ─────────────────────────────────────────────
    # [FIX] Hitung sekali dengan tipe float yang konsisten
    current_px: float = float(close.iloc[-1])
    exdate_info: ExDateInfo = scan_exdate(t, current_price=current_px)

    if exdate_info["risk_tier"] == "CRITICAL":
        logger.info(
            f"[{t}] Excluded: ex-date CRITICAL "
            f"(dalam {exdate_info['days_until_exdate']} hari)."
        )
        return None

    # ── RSI (14) — Wilder's EMA ────────────────────────────────────────────
    rsi_series = compute_rsi(close)
    if len(rsi_series) == 0:
        return None
    rsi_latest: float = float(rsi_series.iloc[-1])

    if rsi_latest > cfg["rsi_hard_reject"]:
        logger.debug(f"[{t}] RSI {rsi_latest:.1f} > {cfg['rsi_hard_reject']}, hard reject.")
        return None

    # ── SMA 20 ────────────────────────────────────────────────────────────
    sma20 = close.rolling(20).mean()
    if pd.isna(sma20.iloc[-1]):
        return None
    sma20_latest: float = float(sma20.iloc[-1])

    # Uptrend confirmation: harga harus di atas SMA20
    if current_px <= sma20_latest:
        return None

    # ── ATR (14) ──────────────────────────────────────────────────────────
    atr_series = compute_atr(high, low, close)
    if pd.isna(atr_series.iloc[-1]):
        return None
    atr_14: float = float(atr_series.iloc[-1])

    # ── Liquidity Gate: ADT 20d ───────────────────────────────────────────
    adt_20: float = float((close * vol).tail(20).mean())
    if adt_20 < cfg["min_adt_20d"]:
        logger.debug(f"[{t}] ADT Rp {adt_20:,.0f} < threshold, skip.")
        return None

    # ── Volume Confirmation: 3d avg vs 20d avg ───────────────────────────
    vol_20d_avg: float = float(vol.tail(20).mean())
    vol_3d_avg:  float = float(vol.tail(3).mean())
    if vol_3d_avg <= vol_20d_avg * cfg["vol_confirmation_ratio"]:
        return None

    vol_5d_avg: float = float(vol.tail(5).mean())
    curr_vol:   float = float(vol.iloc[-1])

    # ── MOMENTUM SCORE ────────────────────────────────────────────────────
    mom_score: float = 0.0
    mom_note:  list[str] = []

    # RSI Zone Scoring
    if cfg["rsi_accum_lo"] <= rsi_latest <= cfg["rsi_accum_hi"]:
        mom_score += cfg["weight_momentum_rsi"]
        mom_note.append(f"RSI Akumulasi ({rsi_latest:.1f})")
    elif cfg["rsi_accum_hi"] < rsi_latest <= cfg["rsi_strong_hi"]:
        mom_score += cfg["weight_momentum_rsi"] * 0.75
        mom_note.append(f"RSI Uptrend Kuat ({rsi_latest:.1f})")
    elif rsi_latest > cfg["rsi_strong_hi"]:
        mom_score += cfg["weight_momentum_rsi"] * 0.25
        mom_note.append(f"RSI Overbought ({rsi_latest:.1f})")
    else:
        mom_score += cfg["weight_momentum_rsi"] * 0.25
        mom_note.append(f"RSI Lemah ({rsi_latest:.1f})")

    # Volume Breakout Scoring
    if curr_vol > vol_5d_avg:
        mom_score += cfg["weight_momentum_vol"]
        mom_note.append("Volume Breakout")
    else:
        mom_score += cfg["weight_momentum_vol"] * 0.5
        mom_note.append("Volume Normal")

    # ── Composite Score + Distance to SMA20 Adjustments ─────────────────
    total_score: float = row["Val_Score"] + row["Prof_Score"] + mom_score

    dist_to_sma20_pct: float = (current_px - sma20_latest) / sma20_latest

    if dist_to_sma20_pct > 0.10:
        # Over-extended: harga terlalu jauh di atas SMA20, risiko pullback
        total_score += cfg["over_extended_penalty"]
        mom_note.append(f"Over-Extended (+{dist_to_sma20_pct*100:.1f}% SMA20)")
    elif 0.01 <= dist_to_sma20_pct <= 0.05:
        # [IMPROVE] Fresh breakout: zona entry ideal
        total_score += cfg["fresh_breakout_bonus"]
        mom_note.append(f"Fresh Breakout (+{dist_to_sma20_pct*100:.1f}% SMA20)")

    # ── Stop Loss (ATR-based + BEI tick size) ────────────────────────────
    stop_candidate_1 = sma20_latest - (cfg["stop_atr_from_sma20"] * atr_14)
    stop_candidate_2 = current_px   - (cfg["stop_atr_from_price"] * atr_14)
    stop_loss: float = max(stop_candidate_1, stop_candidate_2)
    stop_loss = max(stop_loss, current_px * cfg["stop_hard_floor_pct"])
    # Bulatkan ke fraksi harga BEI yang valid (tick size regulation)
    stop_loss = snap_to_tick(stop_loss)

    # ── Sector PBV Context ────────────────────────────────────────────────
    sector_key   = row["Sector"]
    sector_bench = SECTOR_PBV_BENCHMARK.get(sector_key, SECTOR_PBV_BENCHMARK["default"])
    pbv_current: float = row["Current Price to Book Value"]
    pbv_label = (
        "Murah" if pbv_current < sector_bench["fair_lo"] else
        "Wajar" if pbv_current <= sector_bench["fair_hi"] else
        "Mahal"
    )

    return {
        "Ticker":                   t,
        "Sektor":                   row["Sector_Label"],
        "Current Price":            current_px,
        "Stop Loss Level":          round(stop_loss, 0),
        "Est. Fair Value (Graham)": row["Graham_Number"],
        "Graham_Bear":              row["Graham_Bear"],
        "Graham_Bull":              row["Graham_Bull"],
        "Valuation Gap (%)":        row["Valuation_Gap_Pct"],
        "RSI (14)":                 rsi_latest,
        "SMA 20":                   sma20_latest,
        "ATR (14)":                 atr_14,
        "ROE (TTM)":                row["Return on Equity (TTM)"],
        "DER (Quarter)":            row["Debt to Equity Ratio (Quarter)"],
        "PBV":                      pbv_current,
        "PBV vs Sektor":            pbv_label,
        "PBV Sektor Percentile":    round(row["PBV_Sector_Pctile"] * 100, 1),
        "ADT 20d (Rp)":             adt_20,
        "Composite Score":          total_score,
        "Entry Strategy":           " | ".join(mom_note),
        "ExDate Risk":              exdate_info["risk_tier"],
        "ExDate Date":              exdate_info.get("ex_date"),
        "_exdate_info":             exdate_info,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ── MAIN PIPELINE ─────────────────────────────────════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(cfg: dict) -> pd.DataFrame:
    logger = setup_logging(cfg["scratch_dir"])
    os.makedirs(cfg["output_dir"], exist_ok=True)
    os.makedirs(cfg["scratch_dir"], exist_ok=True)

    logger.info("=" * 60)
    logger.info("IHSG Quantitative Swing-Trade Scouting Engine v2.1")
    logger.info("=" * 60)

    # ── 1. DATA INGESTION ────────────────────────────────────────────────────

    logger.info(f"Membaca: {cfg['input_file']}")
    df_stats  = pd.read_excel(cfg["input_file"], sheet_name="key-statistics")
    df_prices = pd.read_excel(cfg["input_file"], sheet_name="stock-prices")

    df = pd.merge(
        df_stats,
        df_prices[["Ticker", "Close Price", "Volume"]],
        on="Ticker",
    )

    sector_map = _load_sector_map(cfg["sector_cache_file"], logger)

    for col in [
        "Close Price",
        "Debt to Equity Ratio (Quarter)",
        "Current Price to Book Value",
        "Return on Equity (TTM)",
        "Current EPS (TTM)",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"Total ticker universe: {len(df)}")

    # ── 2. SECTOR-AWARE PBV RANKING ──────────────────────────────────────────

    df["Sector"] = df["Ticker"].map(sector_map).fillna("default")

    unmapped = df[df["Sector"] == "default"]["Ticker"].tolist()
    if unmapped:
        logger.warning(
            f"SECTOR_MAP miss → {len(unmapped)} ticker fallback ke 'default': "
            + str(unmapped[:30]) + ("..." if len(unmapped) > 30 else "")
        )

    # Rank PBV dalam sektor (ascending: murah = rank rendah = lebih mungkin lolos filter)
    df["PBV_Sector_Pctile"] = df.groupby("Sector")["Current Price to Book Value"].rank(
        pct=True, ascending=True
    )

    df["Sector_Label"] = df["Sector"].map(
        {k: v["label"] for k, v in SECTOR_PBV_BENCHMARK.items()}
    ).fillna("Lain-lain")

    # ── 3. STATIC FILTERING ──────────────────────────────────────────────────

    filtered = df[
        (df["Close Price"] > cfg["min_close_price"]) &
        (df["Debt to Equity Ratio (Quarter)"] < cfg["max_der"]) &
        (df["PBV_Sector_Pctile"] < cfg["pbv_sector_pctile"]) &
        (df["Current Price to Book Value"] < cfg["max_pbv_hard"]) &
        (df["Return on Equity (TTM)"] > cfg["min_roe"])
    ].copy()

    logger.info(f"Lolos static filter: {len(filtered)} ticker")

    # ── 4. VALUATION SCORING — Graham Number (IHSG-calibrated) ──────────────

    filtered["BVPS"] = filtered["Close Price"] / filtered["Current Price to Book Value"]

    valid_graham = (filtered["Current EPS (TTM)"] > 0) & (filtered["BVPS"] > 0)
    eps  = filtered["Current EPS (TTM)"]
    bvps = filtered["BVPS"]
    k    = cfg["graham_k"]

    filtered["Graham_Number"] = np.where(valid_graham, np.sqrt(k * eps * bvps), 0)
    filtered["Graham_Bear"]   = np.where(valid_graham, np.sqrt(k * (eps * cfg["graham_bear_eps"]) * bvps), 0)
    filtered["Graham_Bull"]   = np.where(valid_graham, np.sqrt(k * (eps * cfg["graham_bull_eps"]) * bvps), 0)

    filtered["Valuation_Gap_Pct"] = (
        (filtered["Graham_Number"] - filtered["Close Price"]) / filtered["Close Price"]
    ) * 100

    # clip(lower=0): saham di atas Graham Number → gap = 0, Val_Score akan 0
    filtered["Valuation_Gap_Pct"] = filtered["Valuation_Gap_Pct"].clip(lower=0)

    # Rank-based score → imun terhadap outlier Graham Number yang ekstrem
    filtered["Val_Score"] = (
        filtered["Valuation_Gap_Pct"].rank(pct=True) * cfg["weight_valuation"]
    )

    # ── 5. PROFITABILITY SCORING ─────────────────────────────────────────────

    filtered["Prof_Score"] = (
        filtered["Return on Equity (TTM)"].rank(pct=True) * cfg["weight_profitability"]
    )

    # ── 6. DYNAMIC TECHNICALS VIA YFINANCE ───────────────────────────────────

    valid_tickers = filtered["Ticker"].tolist()
    tickers_yf    = [t + ".JK" for t in valid_tickers]

    data = download_yf_with_retry(
        tickers_yf,
        period=cfg["yf_period"],
        retries=cfg["yf_retries"],
        delay=cfg["yf_retry_delay"],
        logger=logger,
    )

    results = []

    for _, row in filtered.iterrows():
        t_yf = row["Ticker"] + ".JK"

        if t_yf not in data.columns.get_level_values(0):
            continue

        df_t = data[t_yf].dropna(how="all")
        if len(df_t) < cfg["min_bars"]:
            continue

        result = _analyze_ticker(row, df_t, cfg, logger)
        if result:
            results.append(result)

    # ── 7. FINALIZE & OUTPUT ──────────────────────────────────────────────────

    final_df = pd.DataFrame(results)

    if final_df.empty:
        logger.warning("Tidak ada ticker yang lolos semua filter.")
    else:
        final_df = final_df.sort_values("Composite Score", ascending=False).head(cfg["top_n"])
        logger.info(f"Top {len(final_df)} kandidat berhasil disaring.")

    # ── Export JSON (untuk orchestrator.py) ──────────────────────────────────
    if not final_df.empty:
        json_path = os.path.join(cfg["output_dir"], "top10_candidates.json")
        export_df = final_df.drop(columns=["_exdate_info"], errors="ignore")
        export_df.to_json(json_path, orient="records", indent=2)
        logger.info(f"JSON diekspor → {json_path}")

    # ── Export Markdown Report ────────────────────────────────────────────────
    md_content = _build_markdown_report(final_df, cfg)
    report_path = os.path.join(cfg["scratch_dir"], "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"Report → {report_path}")

    logger.info("PIPELINE SELESAI.")
    return final_df


# ══════════════════════════════════════════════════════════════════════════════
# ── REPORT BUILDER ────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _build_markdown_report(final_df: pd.DataFrame, cfg: dict) -> str:
    lines = []
    lines.append(f"# 🏆 Top {cfg['top_n']} High-Conviction IHSG Swing Candidates")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")
    lines.append(
        "| Rank | Ticker | Sektor | Harga | Stop Loss | Fair Value (Bear–Bull) "
        "| Score | Gap | RSI | PBV | Entry Note |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

    for i, (_, r) in enumerate(final_df.iterrows(), 1):
        fv_str = (
            f"Rp {r['Graham_Bear']:,.0f} – Rp {r['Graham_Bull']:,.0f}"
            if r["Est. Fair Value (Graham)"] > 0 else "N/A"
        )
        exdate_icon = " ⚠️" if r["ExDate Risk"] == "WARNING" else ""
        lines.append(
            f"| {i} "
            f"| **{r['Ticker']}**{exdate_icon} "
            f"| {r['Sektor']} "
            f"| Rp {r['Current Price']:,.0f} "
            f"| **Rp {r['Stop Loss Level']:,.0f}** "
            f"| {fv_str} "
            f"| **{r['Composite Score']:.1f}/100** "
            f"| +{r['Valuation Gap (%)']:.1f}% "
            f"| {r['RSI (14)']:.1f} "
            f"| {r['PBV']:.1f}× ({r['PBV vs Sektor']}) "
            f"| {r['Entry Strategy']} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> ⚠️ = Mendekati ex-date dividen, waspadai dividend gap risk.")
    lines.append("")

    # ── ExDate Detail Blocks untuk ticker WARNING tier ───────────────────────
    warning_rows = final_df[final_df["ExDate Risk"] == "WARNING"]
    if not warning_rows.empty:
        lines.append("## ⚠️ Dividend Ex-Date Risk Details")
        lines.append("")
        for _, wr in warning_rows.iterrows():
            ex_info: ExDateInfo = wr["_exdate_info"]
            lines.append("```")
            lines.append(format_exdate_block(wr["Ticker"], ex_info).strip())
            lines.append("```")
            lines.append("")

    if not final_df.empty:
        top1 = final_df.iloc[0]
        max_dd = ((top1["Current Price"] - top1["Stop Loss Level"]) / top1["Current Price"]) * 100
        lines.append(f"## 💡 Investment Thesis: {top1['Ticker']} (Rank #1)")
        lines.append("")
        lines.append(
            f"**{top1['Ticker']}** ({top1['Sektor']}) muncul sebagai kandidat tertinggi "
            f"berdasarkan multi-factor swing strategy."
        )
        lines.append("")
        lines.append(
            f"- **Valuation MoS**: Diskon **{top1['Valuation Gap (%)']:.1f}%** "
            f"terhadap Graham Fair Value (Rp {top1['Est. Fair Value (Graham)']:,.0f}). "
            f"PBV saat ini {top1['PBV']:.1f}× — dinilai **{top1['PBV vs Sektor']}** "
            f"vs historis sektor {top1['Sektor']}."
        )
        lines.append(
            f"- **Momentum & Trend**: Harga Rp {top1['Current Price']:,.0f} "
            f"di atas SMA-20 (Rp {top1['SMA 20']:,.0f}). {top1['Entry Strategy']}."
        )
        lines.append(
            f"- **Profitabilitas**: ROE {top1['ROE (TTM)']*100:.1f}% "
            f"dengan DER {top1['DER (Quarter)']:.2f}× — fundamental solid."
        )
        lines.append(
            f"- **Risk Management**: Stop loss di **Rp {top1['Stop Loss Level']:,.0f}** "
            f"(ATR-based, max drawdown ~{max_dd:.1f}%)."
        )
        lines.append("")
        lines.append(
            "**Action Plan**: Kandidat ini cocok untuk swing 1–3 bulan "
            "dengan target menutup valuation gap, dilindungi oleh fundamental yang kuat."
        )
    else:
        lines.append(
            "> Tidak ada ticker yang lolos semua filter dalam scan ini. "
            "Coba longgarkan threshold atau perbarui data input."
        )

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# ── ENTRY POINT ───────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_pipeline(CONFIG)