import time

from datetime import datetime
from dotenv import load_dotenv

from schemas.fundamental import (
    Fundamental,
    PerShare,
    Solvency,
    ManagementEffectiveness,
    Profitability,
    Growth,
    Dividend,
    MarketRank,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement,
    PricePerformance,
    CurrentValuation,
    Stat,
)
from schemas.sentiment import Sentiment
from schemas.stock import Stock
from schemas.stock_price import StockPrice
from services.stockbit_api_client import StockbitApiClient
from utils.helpers import (
    parse_currency_to_float,
    parse_key_statistic_results_item_value,
)
from utils.logger_config import logger

load_dotenv()


class StockBit:
    """
    A class to interact with the StockBit API and fetch key statistics, stock price, and sentiment for stocks.
    """

    def __init__(self, stocks: [Stock]):
        """
        Initializes the StockBit provider with necessary headers and URL.
        """
        logger.info("StockBit provider initialised")
        self.stocks = stocks
        self.base_url = "https://exodus.stockbit.com"
        self.key_statistic = None
        self.stockbit_api_client = StockbitApiClient()

    def key_statistic_by_stock(self, stock: Stock) -> dict:
        """
        Retrieves key statistics for a given stock by sending a GET request to the API.

        Args:
            stock (Stock): An instance of the Stock class containing the ticker symbol.

        Returns:
            dict: A dictionary containing the key statistics if the request is successful.
            None: If the request fails after retrying or encounters an error.

        Raises:
            requests.exceptions.RequestException: If the request fails due to network issues or invalid URL.

        Side Effects:
            - Logs an error message if the response status code is not 200.
            - Re-authenticates if a 401 Unauthorized status code is received and retries the request up to 3 times.
            - Logs an error message if the request fails due to an exception.
            - Logs an informational message if the request fails after all retries.
        """
        url = f"{self.base_url}/keystats/ratio/v1/{stock.ticker}?year_limit=10"

        return self.stockbit_api_client.get(url)

    def with_fundamental(self):
        """
        Get fundamentals for a list of stocks.

        Returns:
            Self
        """
        processed = 1
        for stock in self.stocks:
            logger.info(
                f"Processing key statistic for: {stock.ticker} ({processed}/{len(self.stocks)})"
            )
            self.key_statistic = self.key_statistic_by_stock(stock)

            if self.key_statistic:
                stock.fundamental = self._fundamental(stock)

            time.sleep(0.1)
            logger.debug(stock)
            processed += 1

        return self

    def _fundamental(self, stock: Stock) -> Fundamental | None:
        """
        Parses the API response data and returns a Fundamental object.

        Args:
            stock (Stock): The Stock object for which the fundamental data is being parsed.

        Returns:
            Fundamental: An object containing parsed fundamental data.
        """

        if self.key_statistic == {}:
            return None

        fundamental = Fundamental()
        fundamental.stock = stock

        data = self.key_statistic["data"]

        # Stats
        #
        stat = Stat(
            parse_currency_to_float(data["stats"]["current_share_outstanding"]),
            parse_currency_to_float(data["stats"]["market_cap"]),
            parse_currency_to_float(data["stats"]["enterprise_value"]),
        )
        fundamental.stat = stat
        logger.debug(stat)

        # -- nested object
        closure_fin_items_results = data["closure_fin_items_results"]

        # Current Valuation
        #
        current_valuation_fin_name_results = closure_fin_items_results[0][
            "fin_name_results"
        ]

        current_valuation = CurrentValuation(
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 0
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 1
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 2
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 3
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 4
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 5
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 6
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 7
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 8
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 9
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 10
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 11
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 12
            ),
            parse_key_statistic_results_item_value(
                current_valuation_fin_name_results, 13
            ),
        )
        fundamental.current_valuation = current_valuation
        logger.debug(current_valuation)

        # Per Share
        #
        per_share_fin_name_results = closure_fin_items_results[1]["fin_name_results"]
        per_share = PerShare(
            parse_key_statistic_results_item_value(per_share_fin_name_results, 0),
            parse_key_statistic_results_item_value(per_share_fin_name_results, 1),
            parse_key_statistic_results_item_value(per_share_fin_name_results, 2),
            parse_key_statistic_results_item_value(per_share_fin_name_results, 3),
            parse_key_statistic_results_item_value(per_share_fin_name_results, 4),
            parse_key_statistic_results_item_value(per_share_fin_name_results, 5),
        )
        fundamental.per_share = per_share
        logger.debug(per_share)

        # Solvency
        #
        solvency_fin_name_results = closure_fin_items_results[2]["fin_name_results"]
        solvency = Solvency(
            parse_key_statistic_results_item_value(solvency_fin_name_results, 0),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 1),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 2),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 3),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 4),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 5),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 6),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 7),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 8),
            parse_key_statistic_results_item_value(solvency_fin_name_results, 9),
        )
        fundamental.solvency = solvency
        logger.debug(solvency)

        # Management Effectivieness
        management_effectiveness_fin_name_results = closure_fin_items_results[3][
            "fin_name_results"
        ]
        management_effectiveness = ManagementEffectiveness(
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 0
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 1
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 2
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 3
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 4
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 5
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 6
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 7
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 8
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 9
            ),
            parse_key_statistic_results_item_value(
                management_effectiveness_fin_name_results, 10
            ),
        )
        fundamental.management_effectiveness = management_effectiveness
        logger.debug(management_effectiveness)

        # Profitability
        #
        profitability_fin_name_results = closure_fin_items_results[4][
            "fin_name_results"
        ]
        profitability = Profitability(
            parse_key_statistic_results_item_value(profitability_fin_name_results, 0),
            parse_key_statistic_results_item_value(profitability_fin_name_results, 1),
            parse_key_statistic_results_item_value(profitability_fin_name_results, 2),
        )
        fundamental.profitability = profitability
        logger.debug(profitability)

        # Growth
        #
        growth_fin_name_results = closure_fin_items_results[5]["fin_name_results"]
        growth = Growth(
            parse_key_statistic_results_item_value(growth_fin_name_results, 0),
            parse_key_statistic_results_item_value(growth_fin_name_results, 1),
            parse_key_statistic_results_item_value(growth_fin_name_results, 2),
        )
        fundamental.growth = growth
        logger.debug(growth)

        # Dividend
        #
        dividend_fin_name_results = closure_fin_items_results[6]["fin_name_results"]
        dividend = Dividend(
            parse_key_statistic_results_item_value(dividend_fin_name_results, 0),
            parse_key_statistic_results_item_value(dividend_fin_name_results, 1),
            parse_key_statistic_results_item_value(dividend_fin_name_results, 2),
            parse_key_statistic_results_item_value(dividend_fin_name_results, 3),
            parse_key_statistic_results_item_value(dividend_fin_name_results, 4),
        )
        fundamental.dividend = dividend
        logger.debug(dividend)

        # Market Rank
        #
        market_rank_fin_name_results = closure_fin_items_results[7]["fin_name_results"]
        market_rank = MarketRank(
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 0),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 1),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 2),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 3),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 4),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 5),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 6),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 7),
            parse_key_statistic_results_item_value(market_rank_fin_name_results, 8),
        )
        fundamental.market_rank = market_rank
        logger.debug(market_rank)

        # Income Statement
        #
        income_statement_fin_name_results = closure_fin_items_results[8][
            "fin_name_results"
        ]
        income_statement = IncomeStatement(
            parse_key_statistic_results_item_value(
                income_statement_fin_name_results, 0
            ),
            parse_key_statistic_results_item_value(
                income_statement_fin_name_results, 1
            ),
            parse_key_statistic_results_item_value(
                income_statement_fin_name_results, 2
            ),
            parse_key_statistic_results_item_value(
                income_statement_fin_name_results, 3
            ),
        )
        fundamental.income_statement = income_statement
        logger.debug(income_statement)

        # Balance Sheet
        #
        balance_sheet_fin_name_results = closure_fin_items_results[9][
            "fin_name_results"
        ]
        balance_sheet = BalanceSheet(
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 0),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 1),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 2),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 3),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 4),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 5),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 6),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 7),
            parse_key_statistic_results_item_value(balance_sheet_fin_name_results, 8),
        )
        fundamental.balance_sheet = balance_sheet
        logger.debug(balance_sheet)

        # Cash Flow
        #
        cash_flow_statement_fin_name_results = closure_fin_items_results[10][
            "fin_name_results"
        ]
        cash_flow_statement = CashFlowStatement(
            parse_key_statistic_results_item_value(
                cash_flow_statement_fin_name_results, 0
            ),
            parse_key_statistic_results_item_value(
                cash_flow_statement_fin_name_results, 1
            ),
            parse_key_statistic_results_item_value(
                cash_flow_statement_fin_name_results, 2
            ),
            parse_key_statistic_results_item_value(
                cash_flow_statement_fin_name_results, 3
            ),
            parse_key_statistic_results_item_value(
                cash_flow_statement_fin_name_results, 4
            ),
        )
        fundamental.cash_flow_statement = cash_flow_statement
        logger.debug(cash_flow_statement)

        # Price Performance
        #
        price_performance_fin_name_results = closure_fin_items_results[11][
            "fin_name_results"
        ]
        price_performance = PricePerformance(
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 0
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 1
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 2
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 3
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 4
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 5
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 6
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 7
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 8
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 9
            ),
            parse_key_statistic_results_item_value(
                price_performance_fin_name_results, 10
            ),
        )
        fundamental.price_performance = price_performance

        return fundamental

    def stock_price_by_stock(self, stock: Stock) -> Stock:
        """
        Fetches the stock price data for a given stock.

        This method constructs a URL using the base URL and the stock's ticker symbol,
        then makes an HTTP GET request to retrieve the stock price data associated with that stock.

        Parameters:
        - stock (Stock): An instance of the Stock class containing the ticker symbol
          for which the stock price data is to be fetched.

        Returns:
        - Stock: The stock price data extracted from the response.
        """
        url = (
            f"{self.base_url}/company-price-feed/v2/orderbook/companies/{stock.ticker}"
        )

        return self.stockbit_api_client.get(url)

    def with_stock_price(self):
        """
        Updates each stock in the stocks list with detailed price data.

        This method iterates over each stock in the `stocks` list, fetching the latest stock price data.
        It updates various attributes of the stock with the retrieved data, such as last price, change, volume, etc.
        The method pauses briefly between processing each stock to avoid overwhelming the server with requests.

        Returns:
        - self: The instance of the class, allowing for method chaining.
        """
        processed = 1
        for stock in self.stocks:
            logger.info(
                f"Processing stock price for: {stock.ticker} ({processed}/{len(self.stocks)})"
            )
            response = self.stock_price_by_stock(stock)

            if response == {}:
                logger.warning(
                    f"Skipped to fetch stock price for {stock.ticker} because empty response!"
                )
                continue

            data = response["data"]

            stock.stock_price = StockPrice(
                price=data["lastprice"],
                change=data["change"],
                fbuy=data["fbuy"],
                fsell=data["fsell"],
                volume=data["volume"],
                percentage_change=data["percentage_change"],
                average=data["average"],
                close=data["close"],
                high=data["high"],
                low=data["low"],
                open=data["open"],
                ara=float(data["ara"]["value"].replace(",", "")),
                arb=float(data["arb"]["value"].replace(",", "")),
                frequency=data["frequency"],
            )

            time.sleep(0.1)

            logger.debug(stock)
            processed += 1

        return self

    def stream_pinned_by_stock(self, stock: Stock) -> dict:
        """
        Fetches the pinned stream data for a given stock.

        This method constructs a URL using the base URL and the stock's ticker symbol,
        then makes an HTTP GET request to retrieve the pinned stream data associated
        with that stock.

        Parameters:
        - stock (Stock): An instance of the Stock class containing the ticker symbol
          for which the pinned stream data is to be fetched.

        Returns:
        - dict: A dictionary containing the response data from the HTTP GET request.
        """
        url = f"{self.base_url}/stream/v3/symbol/{stock.ticker}/pinned"

        return self.stockbit_api_client.get(url)

    def stream_by_stock(self, stock: Stock) -> dict:
        """
        Fetches the stream data for a given stock.

        This method constructs a URL using the base URL and the stock's ticker symbol,
        then makes an HTTP POST request to retrieve the stream data associated with that stock.
        The request includes a payload specifying the category, last stream ID, and limit.

        Parameters:
        - stock (Stock): An instance of the Stock class containing the ticker symbol
          for which the stream data is to be fetched.

        Returns:
        - dict: A dictionary containing the response data from the HTTP POST request.
        """
        url = f"{self.base_url}/stream/v3/symbol/{stock.ticker}"
        payload = {"category": "STREAM_CATEGORY_ALL", "last_stream_id": 0, "limit": 20}
        return self.stockbit_api_client.post(url, payload)

    def with_stream_data(self):
        """
        Updates each stock in the stocks list with sentiment data from stream and pinned stream sources.

        This method iterates over each stock in the `stocks` list, fetching both pinned and regular stream data.
        It processes the response to extract sentiment information, which is then added to the stock's sentiment attribute.
        The method pauses briefly between processing each stock to avoid overwhelming the server with requests.

        Returns:
        - self: The instance of the class, allowing for method chaining.
        """
        processed = 1
        for stock in self.stocks:
            logger.info(
                f"Processing stream data for: {stock.ticker} ({processed}/{len(self.stocks)})"
            )
            response_stream_pinned = self.stream_pinned_by_stock(stock)
            response_stream = self.stream_by_stock(stock)

            if response_stream_pinned != {}:
                pinned_data = response_stream_pinned["data"]

                if pinned_data is not None:
                    posted_at = datetime.fromisoformat(pinned_data["created_at"])
                    sentiment = Sentiment(
                        content=pinned_data["content"], posted_at=posted_at
                    )

                    stock.sentiment = [sentiment]

            if response_stream != {}:
                stream_data = response_stream["data"]["stream"]

                if stream_data is not None:
                    for stream in stream_data:
                        posted_at = datetime.fromisoformat(stream["created_at"])

                        sentiment = Sentiment(
                            content=stream["content"], posted_at=posted_at
                        )

                        if stock.sentiment is None:
                            stock.sentiment = [sentiment]
                        else:
                            stock.sentiment.append(sentiment)

            time.sleep(0.1)
            processed += 1
            logger.debug(stock)

        return self
