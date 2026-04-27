"""
fair_value_calculator.py — Pure-Python fair value engine untuk saham IHSG.

MASALAH YANG DI-SOLVE:
  Sebelumnya fair value dihitung oleh LLM (Flash) dari teks JSON mentah.
  Ini menyebabkan LLM membuat kesalahan aritmatika — misalnya BBCA menghasilkan
  Rp 1.770 padahal range sebenarnya Rp 4.500–Rp 11.375.

SOLUSI:
  Semua kalkulasi dilakukan di Python murni dari data API yang sudah terstruktur.
  Hasilnya (string teks) diinjeksi ke raw_data SEBELUM dikirim ke LLM.
  LLM hanya perlu membaca dan menginterpretasikan angka — bukan menghitungnya.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data container — diisi dari response API Stockbit keystats
# ---------------------------------------------------------------------------

@dataclass
class KeyStats:
    """
    Nilai-nilai fundamental yang dibutuhkan untuk kalkulasi.
    Semua field punya default 0.0 / None agar tidak crash saat data parsial.
    """

    ticker: str = ""

    # Income statement
    eps_ttm: float = 0.0          # Earnings Per Share (Trailing Twelve Months)
    eps_forward: float = 0.0      # EPS proyeksi tahun depan (jika tersedia)
    dps: float = 0.0              # Dividend Per Share (TTM)

    # Balance sheet
    book_value_per_share: float = 0.0   # Ekuitas / jumlah saham beredar

    # Profitability
    roe: float = 0.0              # Return on Equity (desimal: 0.22 = 22%)
    net_margin: float = 0.0       # Net Profit Margin (desimal)
    roa: float = 0.0

    # Market
    current_price: float = 0.0
    shares_outstanding: float = 0.0    # lembar saham beredar (dalam unit, bukan miliar)

    # Historical P/E dan P/B (rata-rata 3-5 tahun, hardcode per sektor atau ambil dari API)
    # Default ini adalah nilai historis konservatif untuk sektor perbankan IHSG
    historical_pe_avg: float = 18.0    # rata-rata P/E historis 5 tahun
    historical_pb_avg: float = 3.5     # rata-rata P/B historis 5 tahun

    # Cost of equity untuk DDM/Gordon Growth (dalam desimal)
    cost_of_equity: float = 0.10       # 10% — default untuk IHSG large cap
    growth_rate: float = 0.07          # 7% — proyeksi pertumbuhan laba jangka panjang

    # Sumber data mentah (untuk debugging)
    raw_pe_current: float = 0.0
    raw_pb_current: float = 0.0


# ---------------------------------------------------------------------------
# Extractor — parse response JSON dari Stockbit keystats API
# ---------------------------------------------------------------------------

def extract_keystats(api_response: dict, ticker: str = "") -> KeyStats:
    """
    Ekstrak field yang relevan dari response raw Stockbit keystats API.
    
    Fungsi ini defensive — setiap field di-try/except agar satu field
    yang hilang tidak crash seluruh kalkulasi.

    Key-name coverage: Stockbit API v1 /keystats/ratio/ mengembalikan struktur
    yang berbeda tergantung endpoint dan versi. Semua pola yang diketahui
    tercakup di bawah; debug log menunjukkan field mana yang berhasil di-parse
    sehingga mudah menambah pola baru jika API berubah.
    
    Args:
        api_response : dict mentah dari Stockbit /keystats/ratio/v1/{ticker}
        ticker       : kode saham (untuk logging)
    
    Returns:
        KeyStats yang sudah diisi, siap untuk FairValueCalculator
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    stats = KeyStats(ticker=ticker)

    def _get(keys: list[str], default: float = 0.0) -> float:
        """Cari nilai dari daftar possible key names, return default jika tidak ada.

        Mendukung dot-notation untuk nested keys (e.g. "data.Current.EPS")
        dan juga pencarian rekursif satu level ke dalam semua sub-dict
        dari api_response untuk menangkap struktur yang tidak terduga.
        """
        for key in keys:
            try:
                val = api_response
                for part in key.split("."):
                    val = val[part]
                if val is not None:
                    return float(val)
            except (KeyError, TypeError, ValueError):
                continue

        # Fallback: cari key sederhana (tanpa dot) di semua sub-dict satu level
        simple_keys = {k.split(".")[-1].lower() for k in keys}
        for top_val in api_response.values():
            if not isinstance(top_val, dict):
                continue
            for k, v in top_val.items():
                if k.lower() in simple_keys and v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        continue

        return default

    # ── Coba berbagai kemungkinan key name dari API Stockbit ────────────────
    # (Key name bisa bervariasi tergantung versi API — list ini defensive)

    stats.eps_ttm = _get([
        "eps", "eps_ttm", "earningPerShare", "earning_per_share",
        "ratios.eps", "keystats.eps", "data.Current.EPS",
        # Stockbit v2 patterns
        "EPS", "EPSTtm", "eps_per_share", "earningsPerShare",
        "data.eps", "summary.eps",
    ])

    stats.eps_forward = _get([
        "eps_forward", "epsForward", "forward_eps",
        "ratios.eps_forward", "EpsForward", "forwardEps",
    ], default=stats.eps_ttm)  # fallback ke TTM jika forward tidak ada

    stats.book_value_per_share = _get([
        "bookValuePerShare", "book_value_per_share", "bvps",
        "ratios.bvps", "keystats.bvps", "data.Current.BVPS",
        # Stockbit v2 patterns
        "BVPS", "BookValuePerShare", "book_value", "bookValue",
        "data.bvps", "summary.bvps", "nav_per_share",
    ])

    stats.dps = _get([
        "dps", "dividendPerShare", "dividend_per_share",
        "ratios.dps", "data.Current.DPS",
        # Stockbit v2 patterns
        "DPS", "DividendPerShare", "dividen_per_share",
        "data.dps", "summary.dps", "dividend",
    ])

    stats.roe = _get([
        "roe", "returnOnEquity", "return_on_equity",
        "ratios.roe", "data.Current.ROE",
        # Stockbit v2 patterns
        "ROE", "ReturnOnEquity", "return_equity",
        "data.roe", "summary.roe",
    ])
    # Normalise: jika ROE dalam persen (misal 22.5), convert ke desimal
    if stats.roe > 1.0:
        stats.roe = stats.roe / 100.0

    stats.net_margin = _get([
        "netMargin", "net_margin", "netProfitMargin",
        "ratios.net_margin", "data.Current.NetProfitMargin",
        # Stockbit v2 patterns
        "NetMargin", "NetProfitMargin", "profit_margin",
        "data.net_margin", "summary.net_margin",
    ])
    if stats.net_margin > 1.0:
        stats.net_margin = stats.net_margin / 100.0

    stats.roa = _get([
        "roa", "returnOnAssets", "return_on_assets",
        "ratios.roa", "data.Current.ROA",
        "ROA", "ReturnOnAssets",
    ])
    if stats.roa > 1.0:
        stats.roa = stats.roa / 100.0

    stats.current_price = _get([
        "price", "lastPrice", "last_price", "close",
        "priceData.last", "Close", "last", "harga",
    ])

    stats.shares_outstanding = _get([
        "sharesOutstanding", "shares_outstanding", "totalShares",
        "outstanding_shares", "SharesOutstanding", "total_shares",
    ])

    stats.raw_pe_current = _get([
        "pe", "priceEarnings", "price_earnings", "per",
        "ratios.pe", "data.Current.PE",
        "PE", "PER", "price_to_earnings",
    ])

    stats.raw_pb_current = _get([
        "pb", "priceBook", "price_book", "pbv",
        "ratios.pb", "data.Current.PBV",
        "PBV", "PB", "price_to_book",
    ])

    # ── Debug log: report what was actually parsed ──────────────────────────
    parsed = {
        "eps_ttm": stats.eps_ttm,
        "bvps": stats.book_value_per_share,
        "dps": stats.dps,
        "roe": f"{stats.roe * 100:.1f}%",
        "pe_current": stats.raw_pe_current,
        "pb_current": stats.raw_pb_current,
    }
    zeros = [k for k, v in parsed.items() if v == 0 or v == "0.0%"]
    if zeros:
        _log.warning(
            f"[FairValue] {ticker}: fields parsed as 0 (likely missing from API): {zeros}. "
            "Fair value may fall back to DDM only or return null. "
            "Check Stockbit API response structure if this is unexpected."
        )
    else:
        _log.info(f"[FairValue] {ticker}: all key stats parsed successfully: {parsed}")

    return stats


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------

class FairValueCalculator:
    """
    Menghitung fair value saham IHSG menggunakan 3 metode:
      1. P/E Band   — EPS × historical average P/E
      2. P/B Band   — BVPS × historical average P/B
      3. DDM / Gordon Growth Model — untuk saham dengan dividen stabil

    Hasil akhir adalah weighted average yang dapat dikonfigurasi per sektor.
    """

    # Bobot default per metode (harus jumlah = 1.0)
    # Untuk bank (BBCA, BBRI, BMRI): P/B lebih relevan karena aset berbasis ekuitas
    SECTOR_WEIGHTS = {
        "bank":        {"pe": 0.35, "pb": 0.45, "ddm": 0.20},
        "consumer":    {"pe": 0.50, "pb": 0.30, "ddm": 0.20},
        "mining":      {"pe": 0.60, "pb": 0.30, "ddm": 0.10},
        "property":    {"pe": 0.30, "pb": 0.55, "ddm": 0.15},
        "default":     {"pe": 0.45, "pb": 0.35, "ddm": 0.20},
    }

    # Ticker → sektor mapping untuk emiten populer IHSG
    TICKER_SECTOR = {
        "BBCA": "bank", "BBRI": "bank", "BMRI": "bank",
        "BBNI": "bank", "BRIS": "bank", "BTPS": "bank",
        "TLKM": "default", "ASII": "default",
        "UNVR": "consumer", "ICBP": "consumer", "MYOR": "consumer",
        "ADRO": "mining", "BYAN": "mining", "MDKA": "mining",
        "BSDE": "property", "SMRA": "property",
    }

    def __init__(self, stats: KeyStats, sector: str | None = None):
        self.stats = stats
        self.sector = sector or self.TICKER_SECTOR.get(stats.ticker.upper(), "default")
        self.weights = self.SECTOR_WEIGHTS[self.sector]

    # ── Metode 1: P/E Band ───────────────────────────────────────────────────

    def fair_value_pe(self) -> float | None:
        """
        Fair value = EPS_TTM × historical_pe_avg
        """
        eps = self.stats.eps_ttm or self.stats.eps_forward
        if eps <= 0 or self.stats.historical_pe_avg <= 0:
            return None
        return round(eps * self.stats.historical_pe_avg, 0)

    # ── Metode 2: P/B Band ───────────────────────────────────────────────────

    def fair_value_pb(self) -> float | None:
        """
        Fair value = BVPS × historical_pb_avg
        """
        bvps = self.stats.book_value_per_share
        if bvps <= 0 or self.stats.historical_pb_avg <= 0:
            return None
        return round(bvps * self.stats.historical_pb_avg, 0)

    # ── Metode 3: DDM (Gordon Growth Model) ─────────────────────────────────

    def fair_value_ddm(self) -> float | None:
        """
        Fair value = DPS / (cost_of_equity - growth_rate)
        """
        dps = self.stats.dps
        ke = self.stats.cost_of_equity
        g = self.stats.growth_rate

        if dps <= 0:
            return None
        if ke <= g:
            return None  # model tidak valid
        if ke - g < 0.03:
            return None  # spread < 3% → DDM too sensitive to be reliable

        fv = dps / (ke - g)

        if self.stats.current_price > 0:
            ratio = fv / self.stats.current_price
            if ratio > 10.0 or ratio < 0.1:
                return None  # outlier — abaikan

        return round(fv, 0)

    # ── Weighted Average ─────────────────────────────────────────────────────

    def fair_value_weighted(self) -> dict:
        pe_fv  = self.fair_value_pe()
        pb_fv  = self.fair_value_pb()
        ddm_fv = self.fair_value_ddm()

        results = {}
        if pe_fv:  results["pe"]  = pe_fv
        if pb_fv:  results["pb"]  = pb_fv
        if ddm_fv: results["ddm"] = ddm_fv

        if not results:
            return {
                "fair_value": None,
                "breakdown": {},
                "confidence": "INSUFFICIENT_DATA",
                "margin_of_safety_pct": None,
                "valuation_verdict": "DATA_UNAVAILABLE",
            }

        total_weight = sum(self.weights[m] for m in results)
        weighted_fv = sum(
            results[m] * (self.weights[m] / total_weight)
            for m in results
        )
        weighted_fv = round(weighted_fv, 0)

        n = len(results)
        confidence = "HIGH" if n == 3 else ("MEDIUM" if n == 2 else "LOW")

        mos = None
        verdict = "DATA_UNAVAILABLE"
        if self.stats.current_price > 0 and weighted_fv > 0:
            mos = round(
                ((weighted_fv - self.stats.current_price) / self.stats.current_price) * 100,
                1
            )
            if mos >= 20:
                verdict = "UNDERVALUED"
            elif mos >= 5:
                verdict = "SLIGHTLY_UNDERVALUED"
            elif mos >= -5:
                verdict = "FAIRLY_VALUED"
            elif mos >= -20:
                verdict = "SLIGHTLY_OVERVALUED"
            else:
                verdict = "OVERVALUED"

        return {
            "fair_value": weighted_fv,
            "breakdown": {k: int(v) for k, v in results.items()},
            "confidence": confidence,
            "margin_of_safety_pct": mos,
            "valuation_verdict": verdict,
        }

    # ── Target & Stop Calculator ─────────────────────────────────────────────

    @staticmethod
    def calculate_trade_levels(
        entry_low: float,
        entry_high: float,
        target_gain_pct: float = 7.0,
        stop_loss_pct: float = 4.0,
    ) -> dict:
        entry_mid    = (entry_low + entry_high) / 2
        target_price = round(entry_mid * (1 + target_gain_pct / 100), -1)
        stop_loss    = round(entry_mid * (1 - stop_loss_pct / 100), -1)

        gain_rp = target_price - entry_mid
        loss_rp = entry_mid - stop_loss
        rr = round(gain_rp / loss_rp, 2) if loss_rp > 0 else 0.0

        return {
            "entry_mid":          round(entry_mid, 0),
            "target_price":       target_price,
            "stop_loss":          stop_loss,
            "expected_return_pct": f"+{target_gain_pct:.1f}%",
            "risk_reward_ratio":  rr,
        }

    # ── Build Report String (untuk diinjeksi ke raw_data) ───────────────────

    def build_report(self, current_price: float | None = None) -> str:
        if current_price is not None:   # ← fix: `if current_price:` is False for 0.0
            self.stats.current_price = current_price

        result = self.fair_value_weighted()
        fv     = result["fair_value"]
        bdown  = result["breakdown"]
        mos    = result["margin_of_safety_pct"]
        conf   = result["confidence"]
        verdict = result["valuation_verdict"]

        lines = [
            "╔══════════════════════════════════════════════════════════════╗",
            "║  FAIR VALUE REPORT — Dihitung Python (Bukan LLM)            ║",
            "║  Gunakan angka ini VERBATIM. Jangan menghitung ulang.        ║",
            "╚══════════════════════════════════════════════════════════════╝",
            "",
            f"TICKER          : {self.stats.ticker}",
            f"SEKTOR          : {self.sector.upper()}",
            f"HARGA PASAR     : Rp {self.stats.current_price:,.0f}",
            "",
            "── BREAKDOWN FAIR VALUE ────────────────────────────────────────",
        ]

        if "pe" in bdown:
            lines.append(
                f"  Metode P/E Band : EPS Rp {self.stats.eps_ttm:,.0f} × "
                f"P/E historis {self.stats.historical_pe_avg:.1f}x "
                f"= Rp {bdown['pe']:,}"
            )
        else:
            lines.append("  Metode P/E Band : TIDAK VALID (EPS = 0 atau data tidak tersedia)")

        if "pb" in bdown:
            lines.append(
                f"  Metode P/B Band : BVPS Rp {self.stats.book_value_per_share:,.0f} × "
                f"P/B historis {self.stats.historical_pb_avg:.1f}x "
                f"= Rp {bdown['pb']:,}"
            )
        else:
            lines.append("  Metode P/B Band : TIDAK VALID (BVPS = 0 atau data tidak tersedia)")

        if "ddm" in bdown:
            lines.append(
                f"  Metode DDM      : DPS Rp {self.stats.dps:,.0f} / "
                f"(ke {self.stats.cost_of_equity*100:.0f}% - g {self.stats.growth_rate*100:.0f}%) "
                f"= Rp {bdown['ddm']:,}"
            )
        else:
            lines.append("  Metode DDM      : TIDAK VALID")

        fv_str = f"Rp {fv:,.0f}" if fv is not None else "Tidak dapat dikalkulasi (Data Kosong / None)"
        lines += [
            "",
            "── HASIL AKHIR ─────────────────────────────────────────────────",
            f"  FAIR VALUE (weighted avg) : {fv_str}",
            f"  Kalkulasi confidence      : {conf} ({len(bdown)}/3 metode valid)",
            "",
        ]

        if mos is not None:
            symbol = "⬆ UPSIDE" if mos >= 0 else "⬇ PREMIUM"
            lines += [
                "── MARGIN OF SAFETY ────────────────────────────────────────────",
                f"  Harga Pasar   : Rp {self.stats.current_price:,.0f}",
                f"  Fair Value    : Rp {fv:,.0f}",
                f"  Gap           : {mos:+.1f}% ({symbol})",
                f"  Verdict       : {verdict}",
                "",
            ]

            if verdict in ("OVERVALUED", "SLIGHTLY_OVERVALUED"):
                premium = abs(mos)
                lines += [
                    "🚨 PERINGATAN OVERVALUATION 🚨",
                    f"   Harga pasar {premium:.1f}% DI ATAS fair value.",
                    "   IMPLIKASI SWING TRADE:",
                    "   • Margin of safety NEGATIF — tidak ada bantalan jika tesis salah.",
                    "   • Entry hanya valid jika ada momentum kuat dan katalis spesifik.",
                    "   • CIO HARUS memberikan rating HOLD atau AVOID kecuali ada alasan",
                    "     teknikal yang sangat kuat untuk override.",
                    "",
                ]
            elif verdict == "UNDERVALUED":
                lines += [
                    "✅ MARGIN OF SAFETY POSITIF",
                    f"   Harga pasar {abs(mos):.1f}% DI BAWAH fair value.",
                    "   Setup swing trade punya bantalan fundamental yang kuat.",
                    "",
                ]

        lines += [
            "── KEY FUNDAMENTALS ────────────────────────────────────────────",
            f"  EPS TTM         : Rp {self.stats.eps_ttm:,.0f}",
            f"  BVPS            : Rp {self.stats.book_value_per_share:,.0f}",
            f"  DPS             : Rp {self.stats.dps:,.0f}",
            f"  ROE             : {self.stats.roe * 100:.1f}%",
            f"  Net Margin      : {self.stats.net_margin * 100:.1f}%",
            f"  P/E saat ini    : {self.stats.raw_pe_current:.1f}x "
                f"(hist avg: {self.stats.historical_pe_avg:.1f}x)",
            f"  P/B saat ini    : {self.stats.raw_pb_current:.1f}x "
                f"(hist avg: {self.stats.historical_pb_avg:.1f}x)",
            "",
            "CATATAN: Semua angka di atas dihitung Python dari data API.",
            "         LLM DILARANG menimpa atau menghitung ulang FAIR VALUE.",
            "═" * 65,
        ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Historical P/E & P/B defaults — override ini per emiten jika punya data lebih akurat
# ---------------------------------------------------------------------------

HISTORICAL_MULTIPLES: dict[str, dict] = {
    "BBCA": {"pe": 25.0, "pb": 4.5, "cost_of_equity": 0.09, "growth_rate": 0.07},
    "BBRI": {"pe": 14.0, "pb": 2.2, "cost_of_equity": 0.10, "growth_rate": 0.06},
    "BMRI": {"pe": 13.0, "pb": 1.8, "cost_of_equity": 0.10, "growth_rate": 0.06},
    "BBNI": {"pe": 10.0, "pb": 1.3, "cost_of_equity": 0.11, "growth_rate": 0.05},
    "TLKM": {"pe": 18.0, "pb": 3.0, "cost_of_equity": 0.09, "growth_rate": 0.05},
    "ASII": {"pe": 14.0, "pb": 1.8, "cost_of_equity": 0.10, "growth_rate": 0.06},
    "UNVR": {"pe": 35.0, "pb": 20.0, "cost_of_equity": 0.09, "growth_rate": 0.05},
    "ICBP": {"pe": 20.0, "pb": 3.5, "cost_of_equity": 0.09, "growth_rate": 0.07},
    "GOTO": {"pe":  0.0, "pb": 3.0, "cost_of_equity": 0.12, "growth_rate": 0.15},  
    "ADRO": {"pe": 8.0,  "pb": 1.5, "cost_of_equity": 0.12, "growth_rate": 0.03},
    "BYAN": {"pe": 7.0,  "pb": 3.5, "cost_of_equity": 0.12, "growth_rate": 0.02},
    "BSDE": {"pe": 10.0, "pb": 0.7, "cost_of_equity": 0.11, "growth_rate": 0.05},
}


def get_historical_multiples(ticker: str) -> dict:
    return HISTORICAL_MULTIPLES.get(ticker.upper(), {
        "pe": 15.0, "pb": 2.0, "cost_of_equity": 0.10, "growth_rate": 0.06
    })


def extract_historical_multiples(api_response: dict, ticker: str) -> dict:
    """Extract 5-year median PE/PB from Stockbit API response.

    Tries multiple common Stockbit API response structures to find
    yearly PE and PB values. Falls back to hardcoded HISTORICAL_MULTIPLES
    if extraction fails or yields insufficient data.
    """
    pe_values: list[float] = []
    pb_values: list[float] = []

    data = api_response.get("data", {})

    # Pattern 1: data.{year}.{metric}  (e.g. data.2024.PE)
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(key, str) and key.isdigit() and isinstance(val, dict):
                for pe_key in ("PE", "pe", "PER", "per"):
                    pe = val.get(pe_key)
                    if pe is not None:
                        try:
                            pv = float(pe)
                            if pv > 0:
                                pe_values.append(pv)
                        except (ValueError, TypeError):
                            pass
                        break
                for pb_key in ("PBV", "pbv", "PB", "pb", "PriceBook"):
                    pb = val.get(pb_key)
                    if pb is not None:
                        try:
                            bv = float(pb)
                            if bv > 0:
                                pb_values.append(bv)
                        except (ValueError, TypeError):
                            pass
                        break

    # Pattern 2: data.historicalRatio (list of dicts)
    hist = data.get("historicalRatio", data.get("historical_ratio", []))
    if isinstance(hist, list):
        for entry in hist:
            if not isinstance(entry, dict):
                continue
            pe = entry.get("PE") or entry.get("pe") or entry.get("PER")
            pb = entry.get("PBV") or entry.get("pb") or entry.get("PB")
            if pe is not None:
                try:
                    pv = float(pe)
                    if pv > 0:
                        pe_values.append(pv)
                except (ValueError, TypeError):
                    pass
            if pb is not None:
                try:
                    bv = float(pb)
                    if bv > 0:
                        pb_values.append(bv)
                except (ValueError, TypeError):
                    pass

    # Start with hardcoded defaults, override with API-derived medians
    result = get_historical_multiples(ticker)
    if len(pe_values) >= 3:
        sorted_pe = sorted(pe_values)
        result["pe"] = round(sorted_pe[len(sorted_pe) // 2], 1)
    if len(pb_values) >= 3:
        sorted_pb = sorted(pb_values)
        result["pb"] = round(sorted_pb[len(sorted_pb) // 2], 1)

    return result


# ---------------------------------------------------------------------------
# Convenience factory — satu baris dari API response ke report string
# ---------------------------------------------------------------------------

def build_fair_value_report(
    api_response: dict,
    ticker: str,
    current_price: float,
) -> tuple[str, float]:
    multiples = extract_historical_multiples(api_response, ticker)
    stats = extract_keystats(api_response, ticker=ticker)

    if multiples.get("pe"): stats.historical_pe_avg = multiples["pe"]
    if multiples.get("pb"): stats.historical_pb_avg = multiples["pb"]
    if multiples.get("cost_of_equity"): stats.cost_of_equity = multiples["cost_of_equity"]
    if multiples.get("growth_rate"): stats.growth_rate = multiples["growth_rate"]

    stats.current_price = current_price

    calc   = FairValueCalculator(stats)
    report = calc.build_report(current_price=current_price)
    result = calc.fair_value_weighted()

    return report, result["fair_value"]