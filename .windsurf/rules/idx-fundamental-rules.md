---
trigger: always_on
---

# Overview

IDX Fundamental Analysis project aims to retrieve and analyse fundamental stock data of companies listed on the
Indonesian Stock Exchange (IDX).

# Stack

- API: FastAPI (under ./app/api)
- UI: Svelte (under ./app/ui)

# Database

- DB: SQLite
- ORM: SQLAlchemy

# Code Convention

- use asynchronus process instead of synchronus.
- global import is priority instead of local import.
- do not overcode with try and except.

# Layer Architecture

This project uses workflow like this:

- view/controller: router api (`./app/api/routers`)
- data transmit/dto: schema (`./schemas`)
- business logic/ service+impl: service (`./services`)
- data access/dao/mapper: repository (`./repositories`)
- model/entity: model (`./db/models`)

# Representations

- Represents data structure as @dataclass inside `./schemas`
- Represents external system class on `./providers`
- Represents db session in `./db/session.py`. Use `get_session` as context manager.
- Represents builders for outputing the result in the excel or spreadsheet.
- Represents business logic inside service class on `./services`

# Tests

- Always generate test case for code you generate.
- Create test on `./tests/` folder.
- Make sure the test is pass using pytest.

# Constraints

- always define asynchronus function in router
- Put the docs or unecessary file you generated under `./tmp`
