from fastapi.responses import JSONResponse
from typing import Any
import json


class MsgSpecJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.encode(content)
