import argparse
from datetime import date

from dotenv import load_dotenv

from builders.analysers import Analyser
from builders.database_builder import DatabaseBuilder
from db import database
from providers.idx import IDX
from providers.stockbit import StockBit
from utils.logger_config import logger

load_dotenv()


def parse_arguments():
    parser = argparse.ArgumentParser(description="IDX Composite Fundamental Analysis")
    parser.add_argument(
        "-f",
        "--full-retrieve",
        action="store_true",
        help="Retrieve full stock data from IDX",
    )
    parser.add_argument(
        "-o",
        "--output-format",
        choices=["spreadsheet", "excel"],
        default="spreadsheet",
        help="Specify the output format: 'spreadsheet' for Google Spreadsheet, 'excel' for Excel file",
    )
    return parser.parse_args()


def main():
    logger.info("IDX Composite Fundamental Analysis")

    args = parse_arguments()

    # Setup database
    database.setup_db(is_drop_table=True)

    # Retrieve stocks from IDX
    idx = IDX(is_full_retrieve=args.full_retrieve)
    stocks = idx.stocks()
    logger.debug("Stocks: {}".format(stocks))
    logger.info("Total Stocks: {}".format(len(stocks)))

    # Process stocks key statistics, price, fundamental, and stream data (news) from Stockbit
    StockBit(stocks=stocks).with_stock_price().with_fundamental().with_stream_data()

    # Analyser to build the output
    title = f"IDX Fundamental Analysis {date.today().strftime('%Y-%m-%d')}"
    Analyser(stocks=stocks).build(output=args.output_format, title=title)

    # Populate to database
    database_builder = DatabaseBuilder(stocks=stocks)
    database_builder.insert_stock()
    database_builder.insert_key_statistic()
    database_builder.insert_key_analysis()
    database_builder.insert_stock_price()
    database_builder.insert_sentiment()


if __name__ == "__main__":
    main()
