import asyncio
from services.debate_chamber import DebateChamber

async def main():
    chamber = DebateChamber()
    
    # Ambil ticker #1 dari top10_candidates.json
    result = await chamber.run("GJTL", current_price=1175.0)
    
    # Checkpoint 1: Tidak ada error
    assert result.get("error") is None, f"Error: {result['error']}"
    
    # Checkpoint 2: ExDate block masuk ke raw_data
    raw = result.get("raw_data", "")
    assert "DIVIDEND EX-DATE SCAN" in raw, "ExDate block tidak diinjeksi ke raw_data!"
    print("✅ ExDate block terinjeksi ke debate context")
    
    # Checkpoint 3: final_verdict valid
    import json
    verdict = json.loads(result["final_verdict"])
    print(f"✅ Verdict: {verdict['rating']} | Confidence: {verdict['confidence']}")
    print(f"   Target : Rp {verdict.get('target_price') or 0.0:,.0f}")
    print(f"   Stop   : Rp {verdict.get('stop_loss') or 0.0:,.0f}")
    print(f"   R/R    : {verdict.get('risk_reward_ratio')}")
    
    # Checkpoint 4: Jika ExDate WARNING, apakah CIO menyebutnya di reasoning?
    reasoning = verdict.get("weighted_reasoning", "")
    if "WARNING" in raw:
        if "dividend" in reasoning.lower() or "ex-date" in reasoning.lower():
            print("✅ CIO acknowledged ex-date risk dalam reasoning")
        else:
            print("⚠️  CIO tidak menyebut ex-date risk — perlu review prompt")
    else:
        print("✅ No ExDate WARNING found for GJTL, skipping reasoning check.")

    # DIAGNOSTIC CHECK
    raw_data = result.get("raw_data", "")
    fv_lines = [l for l in raw_data.splitlines() if "FAIR VALUE" in l.upper()]
    print(f"\n--- FV Lines Found in raw_data ---")
    for l in fv_lines:
        print(repr(l))

    print(f"\nfair_value_estimate dari state: {result.get('fair_value_estimate', 'KEY NOT FOUND')}")

asyncio.run(main())
