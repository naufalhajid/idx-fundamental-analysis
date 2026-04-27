# test_exdate_quick.py — jalankan ini dulu, taruh di root project
from utils.exdate_scanner import scan_exdate, format_exdate_block

# Pilih 3 ticker: satu blue chip, satu mid-cap, satu yang diketahui punya dividen
test_tickers = [
    ("BBRI", 4800.0),   # Blue chip — dividen rutin
    ("TLKM", 3200.0),   # Mid-large — dividen rutin
    ("BUKA", 120.0),    # Tech — kemungkinan tidak ada dividen
]

for ticker, price in test_tickers:
    print(f"\n{'='*50}")
    print(f"Testing: {ticker} @ Rp {price:,.0f}")
    result = scan_exdate(ticker, current_price=price)
    print(f"Risk Tier  : {result['risk_tier']}")
    print(f"Source     : {result['source']}")
    print(f"Ex-Date    : {result['ex_date']}")
    print(f"Days Until : {result['days_until_exdate']}")
    print(f"Div/Share  : {result['div_per_share']}")
    print(f"Div Yield  : {result['div_yield_pct']}%")
    print("\n--- Formatted Block ---")
    print(format_exdate_block(ticker, result))
