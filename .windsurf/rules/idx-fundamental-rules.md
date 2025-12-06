---
trigger: always_on
---

# Overview

IDX Fundamental Analysis project aims to retrieve and analyse fundamental stock data of companies listed on the
Indonesian Stock Exchange (IDX).

# Database

- DB: SQLite
- ORM: SQLAlchemy

# Code Convention

- global import is priority instead of local import.
- do not overcode with try and except.

# Representations

- Represents data structure as Pydantic model inside `./schemas`
- Represents external system class on `./providers`
- Represents db session in `./db/session.py`. Use `get_session` as context manager.
- Represents builders for outputing the result in the excel or spreadsheet.
- Represents business logic inside service class on `./services`

# Tests

- Always generate test case for code you generate.
- Create test on `./tests/` folder.
- Make sure the test is pass using pytest.
