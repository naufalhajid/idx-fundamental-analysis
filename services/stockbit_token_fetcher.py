import logging
import os
import tempfile

from seleniumwire import webdriver
from utils.logger_config import logger

for _name in (
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.remote.remote_connection",
    "seleniumwire",
):
    logging.getLogger(_name).setLevel(logging.WARNING)


class StockbitTokenFetcher:
    def __init__(self):
        self.login_url = "https://stockbit.com/login"
        self.sample_url = "exodus.stockbit.com/chat/v2/rooms/unread/count"

        profile_dir = os.path.join(
            os.path.expanduser("~"), ".idx-fundamental-stockbit-profile"
        )
        os.makedirs(profile_dir, exist_ok=True)

        cache_dir = os.path.join(profile_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)

        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument(f"--disk-cache-dir={cache_dir}")

        self.driver = webdriver.Chrome(options=options)

        tmp_dir = tempfile.gettempdir()
        self.token_path = os.path.join(tmp_dir, "stockbit_token.tmp")
        self.refresh_path = os.path.join(tmp_dir, "stockbit_refresh_token.tmp")

    def fetch_tokens(self):
        driver = self.driver
        driver.get(self.login_url)

        logger.info("Please log in to Stockbit in the opened browser.")
        input("Press Enter here AFTER login succeeds... ")

        sample_request = None
        for req in driver.requests:
            if not req.response:
                continue
            if self.sample_url in req.url:
                sample_request = req

        if sample_request is not None:
            auth_header = sample_request.headers.get(
                "Authorization"
            ) or sample_request.headers.get("authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.error(
                    "Could not find Bearer token in Authorization header for unread count request."
                )
                return None, None

            access_token = auth_header.split(" ", 1)[1]

            refresh_token = ""
            try:
                with open(self.refresh_path, "r") as file:
                    existing_refresh = file.read().strip()
                    if existing_refresh:
                        refresh_token = existing_refresh
            except FileNotFoundError:
                pass
        else:
            logger.error("Could not find sample request for unread count. Try again.")
            return None, None

        logger.info("Access and refresh tokens captured; writing to temp files.")

        with open(self.token_path, "w") as f:
            f.write(access_token)

        with open(self.refresh_path, "w") as f:
            f.write(refresh_token)

        logger.info(f"Tokens written to: {self.token_path} and {self.refresh_path}")

        return access_token, refresh_token

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass
