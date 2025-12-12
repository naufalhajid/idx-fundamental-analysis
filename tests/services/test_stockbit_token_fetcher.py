import unittest

from services.stockbit_token_fetcher import StockbitTokenFetcher


class TestStockbitTokenFetcherReal(unittest.TestCase):
    def test_fetch_tokens_interactive(self):
        """Integration-style test that opens a real browser and requires manual login."""

        fetcher = StockbitTokenFetcher()
        access_token = None

        try:
            access_token = fetcher.fetch_tokens()
        finally:
            fetcher.close()

        self.assertIsInstance(access_token, str)
        self.assertNotEqual(access_token, "")


if __name__ == "__main__":
    unittest.main()
