import os
import tempfile
import time

import requests

from utils.logger_config import logger
from services.stockbit_token_fetcher import StockbitTokenFetcher


class StockbitApiClient:
    """
    Handles HTTP requests to the Stockbit API, including authentication and retries.
    """

    def __init__(self):
        """
        Initializes the StockbitHttpRequest with a URL and optional headers.
        Authenticates with the Stockbit API upon initialization.

        Parameters:
        - headers (dict): Optional headers for the HTTP request.
        """
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:137.0) Gecko/20100101 Firefox/137.0",
        }

        self.is_authorise = False

        self.token_temp_file_path = os.path.join(
            tempfile.gettempdir(), "stockbit_token.tmp"
        )

        self.refresh_token_temp_file_path = os.path.join(
            tempfile.gettempdir(), "stockbit_refresh_token.tmp"
        )

        self._initialize_token_file()

    def _request(self, url: str, method: str, payload: dict = None):
        """
        Makes an HTTP request with the specified method and payload, retrying on failure.

        Parameters:
        - method (str): The HTTP method ("GET" or "POST").
        - payload (dict): Optional payload for POST requests.

        Returns:
        - dict: The JSON response from the server, or an empty dictionary on failure.
        """
        retry = 0
        while retry <= 3:
            try:
                if method == "GET":
                    response = requests.get(url, headers=self.headers)
                elif method == "POST":
                    response = requests.post(url, headers=self.headers, json=payload)
                else:
                    raise ValueError("Unsupported HTTP method")

                logger.debug(url)
                logger.debug(response.status_code)
                logger.debug(response.json())

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(
                        f"Error: Received status code {response.status_code}, "
                        f"text: {response.text}, "
                        f"retry: {retry}"
                    )
                    if response.status_code == 401:
                        self._authenticate_stockbit()
                        retry += 1
                    else:
                        break

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e} retry: {retry}")
                break

            time.sleep(0.2)

        logger.error(f"Failed to retrieve key statistics retry: {retry}")
        return {}

    def get(self, url: str):
        """
        Performs a GET request using the stored URL and headers.

        Returns:
        - dict: The JSON response from the server, or an empty dictionary on failure.
        """
        return self._request(url, "GET")

    def post(self, url: str, payload: dict):
        """
        Performs a POST request using the stored URL, headers, and provided payload.

        Parameters:
        - payload (dict): The payload for the POST request.

        Returns:
        - dict: The JSON response from the server, or an empty dictionary on failure.
        """
        return self._request(url, "POST", payload)

    def _authenticate_stockbit(self):
        """
        Authenticates with the Stockbit API and updates the authorization header.
        Get refresh token if the token is expired
        Login if needed
        """

        if self.is_authorise and not self._is_refresh_token_empty():
            self._refresh_token()
        else:
            self._login()

    def _login(self):
        """
        Login to Stockbit API.
        """
        self.headers["Authorization"] = None

        token = None
        refresh_token = None

        fetcher = None
        try:
            fetcher = StockbitTokenFetcher()
            token, refresh_token = fetcher.fetch_tokens()
        except Exception as e:
            logger.error(f"Failed to fetch tokens via StockbitTokenFetcher: {e}")
        finally:
            if fetcher is not None:
                try:
                    fetcher.close()
                except Exception:
                    pass

        if token:
            logger.info("Logged in successfully via StockbitTokenFetcher!")
            self.headers["Authorization"] = f"Bearer {token}"
            self._write_token(token, refresh_token or "")
            self.is_authorise = True
        else:
            logger.error("Failed to log in via StockbitTokenFetcher.")
            self.is_authorise = False

        time.sleep(1)

    def _refresh_token(self):
        """
        Refreshes new token using refresh token.
        """
        url = "https://exodus.stockbit.com/login/refresh"

        with open(self.refresh_token_temp_file_path, "r") as file:
            self.headers["Authorization"] = f"Bearer {file.read()}"

            try:
                response = requests.post(url, headers=self.headers)

                if response.status_code == 200:
                    logger.info("Token is successfully refreshed!")

                    token = response.json()["data"]["access"]["token"]
                    refresh_token = response.json()["data"]["refresh"]["token"]

                    self.headers["Authorization"] = f"Bearer {token}"

                    self._write_token(token, refresh_token)

                    self.is_authorise = True
                else:
                    logger.error(
                        f"Error: Received status code {response.status_code} - {response.text}"
                    )
                    self._login()

                time.sleep(1)

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")

    def _write_token(self, token, refresh_token):
        """
        Write tokens to temporary file.
        :param token:
        :param refresh_token:
        :return:
        """
        with open(self.token_temp_file_path, "w") as file:
            file.write(token)

        with open(self.refresh_token_temp_file_path, "w") as file:
            file.write(refresh_token)

    def _initialize_token_file(self):
        """
        Intialize token files
        :return:
        """
        try:
            with open(self.refresh_token_temp_file_path, "r") as file:
                file.read()
        except FileNotFoundError:
            with open(self.refresh_token_temp_file_path, "w") as file:
                file.write("")

        try:
            with open(self.token_temp_file_path, "r") as file:
                token = file.read()
                logger.debug(f"Token: {token}")
                if token != "":
                    self.headers["Authorization"] = f"Bearer {token}"

                self._request_challenge()
        except FileNotFoundError:
            with open(self.token_temp_file_path, "w") as file:
                file.write("")

    def _is_refresh_token_empty(self) -> bool:
        """
        Check if token is empty.
        :return: boolean
        """
        try:
            with open(os.path.join(self.refresh_token_temp_file_path), "r") as file:
                token = file.read()
                return token == ""
        except FileNotFoundError:
            return False

    def _request_challenge(self):
        """
        Check expired token by request to light API
        :return:
        """
        try:
            response = requests.get(
                "https://exodus.stockbit.com/research/indicator/new",
                headers=self.headers,
            )

            if response.status_code != 200:
                logger.error(
                    f"Error: Received status code {response.status_code} - {response.text}"
                )
                self._authenticate_stockbit()
            else:
                logger.info("Logged in successfully with existing token!")

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
