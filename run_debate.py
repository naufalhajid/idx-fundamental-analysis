import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from services.debate_chamber import DebateChamber
from utils.logger_config import logger

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stock Debate Chamber — Adversarial Multi-Agent Analysis",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="List of stock tickers to debate (e.g., BBRI BBCA TLKM)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/debates",
        help="Directory to save debate reports (default: output/debates)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # LLM instances created once, reused for all tickers
    chamber = DebateChamber()

    for ticker in args.tickers:
        logger.info(f"{'=' * 60}")
        logger.info(f"Starting debate for: {ticker}")
        logger.info(f"{'=' * 60}")

        result = await chamber.run(ticker)

        if result.get("error") is not None:
            logger.error(f"Debate aborted for {ticker}: {result['error']}")
            continue

        # Save full result
        report = {
            "ticker": result["ticker"],
            "verdict": json.loads(result["final_verdict"]) if result["final_verdict"] else {},
            "debate_rounds": result["round_count"],
            "debate_history": [
                {"role": m.role, "content": m.content, "round": m.round_num}
                for m in result["debate_history"]
            ],
            "raw_data_summary": result["raw_data"],
        }

        report_path = output_dir / f"{ticker}_debate.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Report saved to {report_path}")

        # State is local to this iteration — goes out of scope cleanly
        # No explicit gc.collect() needed

    logger.info("All debates complete.")


if __name__ == "__main__":
    asyncio.run(main())
