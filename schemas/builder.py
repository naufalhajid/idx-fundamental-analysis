from enum import Enum


class BuilderOutput(str, Enum):
    EXCEL = "excel"
    SPREADSHEET = "spreadsheet"
