# LLM App (Python)

A minimal Python app that calls **OpenAI**, **Anthropic**, or **Ollama** (local) chat APIs through a single, unified client.

## Features
- One `chat()` method works for OpenAI, Anthropic, and Ollama (`llm_app/client.py`)
- Secrets live in `.env` (git-ignored); template provided as `.env.example`
- Unit tests run **without** any network calls or API keys (SDKs are mocked)

## Requirements
- Python **3.10+**
- An OpenAI **or** Anthropic API key, **or** a local [Ollama](https://ollama.com/) setup (no key needed)

## Setup

> Windows note: if `python` isn't recognised, install Python 3.10+ from
> https://www.python.org/downloads/ (make sure to tick **“Add python.exe to PATH”**).

1. **Create & activate a virtual environment**
   - Windows (PowerShell):
     ```powershell
     py -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - macOS / Linux:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   *(or use the dev extra: `pip install -e ".[dev]"`)*

3. **Configure your API key**
   ```powershell
   Copy-Item .env.example .env    # Windows
   # cp .env.example .env         # macOS / Linux
   ```
   Then edit `.env`:
   - set `LLM_PROVIDER=openai` **or** `LLM_PROVIDER=anthropic`, or `LLM_PROVIDER=ollama`
   - paste the matching `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`

    - for Ollama: no API key needed, just set OLLAMA_MODEL and OLLAMA_BASE_URL

4. **(Optional) Use a local model via [Ollama](https://ollama.com/)**

   ```bash
   # 1. Pull a model (e.g. llama3)
   ollama pull llama3

   # 2. In .env, set:
   #    LLM_PROVIDER=ollama
   #    OLLAMA_MODEL=llama3          # any model you've pulled
   #    OLLAMA_BASE_URL=http://localhost:11434/v1
   #
   #    No API key is required.
   ```

## Run
```bash
python main.py                       # default question
python main.py "Explain RAG in 2 sentences"
```

## Tests
```bash
pytest
```

## Project layout
```
.
├── .env.example          # template for secrets (commit this)
├── .gitignore
├── main.py               # entry point / demo
├── pyproject.toml        # project metadata + pytest config
├── requirements.txt
├── llm_app/
│   ├── __init__.py
│   ├── config.py         # load settings from .env
│   └── client.py         # unified chat() for OpenAI & Anthropic
└── tests/
    ├── __init__.py
    └── test_client.py
```

## Usage in your own code
```python
from llm_app import LLMClient

client = LLMClient()                       # reads .env
print(client.chat([{"role": "user", "content": "Hi!"}], system="Be brief."))
```
