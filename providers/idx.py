"""
IDX Class Documentation
==========================

**Class Description**
--------------------

The `IDX` class is a provider for retrieving stock data from the IDX (Indonesian Stock Exchange) website.
It uses Selenium WebDriver to interact with the website and extracts relevant data from the stock list page.

**Class Methods**
----------------

### `__init__`

*   Initializes the `IDX` provider with a Chrome WebDriver instance and sets the base URL for the IDX website.
*   Logs a debug message indicating the provider has been initialized.

### `stocks`

*   Retrieves a list of stock data from the IDX website.
*   Returns a list of `Stock` objects, each containing the following attributes:
    + `ticker`: The stock ticker symbol.
    + `name`: The stock name.
    + `ipo_date`: The initial public offering date.
    + `market_cap`: The market capitalization (float).
    + `note`: The stock note.

**Notes**
------

*   The `stocks` method uses Selenium WebDriver to navigate to the IDX website, wait for the table to load,
    and extract the relevant data.
*   The method uses XPath expressions to locate the table elements and extract the data.

"""

import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as expect
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from schemas.stock import Stock
from utils.logger_config import logger


class IDX:
    """
    IDX Provider Class
    """

    def __init__(self, is_full_retrieve=True, is_second_page=False):
        """
        Initializes the IDX provider with a Chrome WebDriver instance and sets the base URL for the IDX website.
        """
        logger.info("IDX provider initialised")
        self.base_url = "https://idx.co.id"
        self.driver = webdriver.Chrome()
        self.is_full_retrieve = is_full_retrieve
        self.is_second_page = is_second_page

    def stocks(self) -> [Stock]:
        """
        Retrieves a list of stock data from the IDX website.

        Returns:
            [Stock]: list of Stock object containing parsed stock data.
        """
        url = f"{self.base_url}/id/data-pasar/data-saham/daftar-saham/"

        self.driver.get(url)

        # if true it will retrieve all stocks, otherwise 10 stocks only
        if self.is_full_retrieve:
            # Wait for the table to be present
            WebDriverWait(self.driver, 3).until(
                expect.presence_of_element_located((By.NAME, "perPageSelect"))
            )

            # # Find the dropdown
            rows_per_page_dropdown = Select(
                self.driver.find_element(By.NAME, "perPageSelect")
            )

            # Select the option to retrieve all stocks
            rows_per_page_dropdown.select_by_value("-1")

        if self.is_second_page:
            # go to second page
            WebDriverWait(self.driver, 3).until(
                expect.presence_of_element_located((By.NAME, "perPageSelect"))
            )

            third_button = self.driver.find_element(
                By.CSS_SELECTOR, "button.footer__navigation__page-btn:nth-child(4)"
            )

            third_button.click()

            # go to second page
            WebDriverWait(self.driver, 3).until(
                expect.presence_of_element_located((By.NAME, "perPageSelect"))
            )

            third_button = self.driver.find_element(
                By.CSS_SELECTOR, "button.footer__navigation__page-btn:nth-child(4)"
            )

            third_button.click()

        # Wait for the table to update, adjust the time if necessary
        WebDriverWait(self.driver, 3).until(
            expect.presence_of_element_located((By.XPATH, '//*[@id="vgt-table"]'))
        )

        # Find the table
        table = self.driver.find_element(By.XPATH, '//*[@id="vgt-table"]')

        # Parse tables by XPATH, the way to find XPATH is by inspect element
        # This is the XPATH for first ticker: table/tbody/tr[1]/td[1]/span
        # Select all row means no index for tr tag.
        tickers = table.find_elements(By.XPATH, "./tbody/tr/td[1]/span")
        names = table.find_elements(By.XPATH, "./tbody/tr/td[2]/span")
        ipo_dates = table.find_elements(By.XPATH, "./tbody/tr/td[3]/span")
        market_caps = table.find_elements(By.XPATH, "./tbody/tr/td[4]/span")
        notes = table.find_elements(By.XPATH, "./tbody/tr/td[5]/span")

        # Append data, use array of stock schema
        stocks = []
        for index in range(len(tickers)):
            stock = Stock(
                ticker=tickers[index].text,
                name=names[index].text,
                ipo_date=ipo_dates[index].text,
                market_cap=float(re.sub(r"\D", "", market_caps[index].text)),
                note=notes[index].text,
            )
            stocks.append(stock)

        # Close browser
        self.driver.quit()

        logger.info(f"Stocks has been retrieved from {url}")
        return stocks
