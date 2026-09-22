"""Dev entrypoint: `python main.py`. Equivalent to `uvicorn app.main:app --reload`.

Kept separate from `app/main.py` (the FastAPI app itself) so the app module
stays importable/testable without also being "the script you run".
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
