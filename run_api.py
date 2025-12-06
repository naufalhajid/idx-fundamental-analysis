import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        app="app.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_excludes=[os.path.abspath(".venv")],
    )
