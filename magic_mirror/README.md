# MagicMirror - Screen Translation Tool

Real-time screen region translation overlay. Captures a screen area via OCR, translates via LLM API, and renders the result as a transparent overlay.

## Quick Start

### From Source

```bash
# 1. Install dependencies
pip install -r magic_mirror/requirements.txt

# 2. Configure API (see Configuration section below)

# 3. Run
python -m magic_mirror.main

# Debug mode
python -m magic_mirror.main --debug
```

### From Packaged EXE

Release package structure:

```
MagicMirror/
  MagicMirror.exe
  llm_providers.example.yaml   <-- rename to llm_providers.yaml
  .env.example                 <-- rename to .env
  README.md
  _internal/
```

First-time setup:

1. Rename `llm_providers.example.yaml` to `llm_providers.yaml`, edit with your API settings
2. Rename `.env.example` to `.env`, fill in your API credentials
3. Double-click `MagicMirror.exe`

## Configuration

### LLM Backend (OpenAI-Compatible API)

MagicMirror uses the **OpenAI-compatible API** protocol for translation. Any LLM service that implements this protocol can be used, including:

- OpenAI (GPT-4, GPT-3.5, etc.)
- Azure OpenAI Service
- Self-hosted models via vLLM, Ollama, LM Studio, LocalAI, etc.
- Any proxy or gateway that exposes an OpenAI-compatible `/v1/chat/completions` endpoint

### llm_providers.yaml

Rename `llm_providers.example.yaml` to `llm_providers.yaml` and edit:

```yaml
default_provider: "my_provider"

providers:
  my_provider:
    type: "openai_compatible"
    base_url: "https://your-api-endpoint:port"     # API base URL
    model: "your-model-name"                        # e.g. gpt-4, llama3, etc.
    headers:                                        # optional custom headers
      useLegacyCompletionsEndpoint: "false"
      X-Tenant-ID: "default_tenant"
    timeout: 60                                     # request timeout (seconds)
    max_retries: 2                                  # retry count on failure
    stream: false                                   # true = streaming translation
    ssl_verify: false                               # false for self-signed certs
```

#### Examples

**OpenAI:**
```yaml
providers:
  openai:
    type: "openai_compatible"
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o-mini"
    timeout: 30
    stream: true
```

**Ollama (local):**
```yaml
providers:
  ollama:
    type: "openai_compatible"
    base_url: "http://localhost:11434/v1"
    model: "llama3"
    timeout: 120
    stream: true
    ssl_verify: false
```

### .env

Rename `.env.example` to `.env` and fill in:

```
API_TOKEN=your_api_token_here
```

The `API_TOKEN` is injected as the `api_key` for the OpenAI client. If your local model (e.g. Ollama) doesn't require authentication, you can leave it as any non-empty string.

### Config file lookup order

| Environment | Lookup path |
|-------------|-------------|
| Packaged EXE | Same folder as `MagicMirror.exe` |
| Source / dev | `magic_mirror/config/` |

Sensitive files (`.env`, `llm_providers.yaml`) are **never** bundled into the EXE. Only the `.example` templates are included in the release package.

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+T` | Select screen region and translate |
| `Ctrl+Alt+C` | Select screen region and extract text (OCR only) |
| `Esc` | Close the most recent overlay |
| `Ctrl+Shift+Esc` | Close all overlays |

## Overlay Behavior

- The overlay is display-only: left-click passes through to underlying windows
- Right-click on the overlay opens a context menu (copy, retranslate, chat, close)
- Keyboard input is not captured by the overlay

## Build

```bash
build_release_magicmirror.bat
```

Output: `release/MagicMirror-v{VER}/MagicMirror/`

The release package includes `.example` config templates. Users must rename and edit them before running.
