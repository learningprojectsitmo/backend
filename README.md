# Backend

[Wiki](wiki/index.md)

# Run
In order to run the backend:
1. Install **uv** on your system
2. cd into the backend repository, run `uv sync` - the project dependencies will be installed in a virtual environment
3. `uv run main.py` or  `source .venv/bin/activate; uvicorn main:app --host 0.0.0.0 --reload` will run the server, it will be available at *localhost:8000*
