# ai-l2-jahnwi — Weekend Wizard (AI Agent + MCP)

> **AI Level 2 Training Project**

An AI agent that plans a fun weekend. You ask in plain English (*"Plan a mystery day in Paris"*), and the agent decides which tools to call, one step at a time (the **ReAct** pattern: think → act → observe → repeat), then writes an itinerary from the real results.

The tools live in a separate **MCP (Model Context Protocol) server**, so the agent discovers and calls them through a standard protocol instead of hard-coded functions.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | `llama-3.3-70b-versatile` via the Groq API (OpenAI-compatible) |
| **Tools** | MCP server built with `FastMCP` (`mcp` 1.x), run over stdio |
| **Backend** | Python · FastAPI · Uvicorn |
| **Frontend** | HTML · CSS · Vanilla JavaScript |

## Tools (in `server_fun.py`)

| Tool | What it does | Data source |
|---|---|---|
| `city_to_coords(city)` | City name → latitude/longitude | Open-Meteo Geocoding |
| `get_weather(latitude, longitude)` | Current temperature, weather code, wind | Open-Meteo |
| `book_recs(topic, limit)` | Book suggestions for a topic | Open Library |
| `random_joke()` | A safe, single-line joke | JokeAPI |
| `random_dog()` | A random dog photo URL | Dog CEO |
| `trivia()` | A multiple-choice trivia question | Open Trivia DB |

None of these APIs need a key. Only the Groq key is required.

---

## Quick Start

### Prerequisites
- Python 3.10+
- A Groq API key (free at [console.groq.com](https://console.groq.com))
- Internet connection

### Install & Run

```bash
# 1. Install dependencies (run this again after every update — new packages may have been added)
pip install -r requirements.txt

# 2. Configure your API key
cp .env.example .env        # Windows: copy .env.example .env
# then edit .env and set GROQ_API_KEY

# 3a. Web app
python app.py
# open http://localhost:8000

# 3b. Or the command-line version
python agent_fun.py
```

### Configuration (`.env`)

```bash
GROQ_API_KEY=your-groq-api-key
MODEL=llama-3.3-70b-versatile   # optional, web app only
HOST=127.0.0.1                  # optional; 0.0.0.0 exposes it on your network
PORT=8000                       # optional
```

---

## Project Structure

```
ai-l2-jahnwi/
├── app.py            # Web app: FastAPI server + ReAct agent loop (max 10 steps)
├── agent_fun.py      # Same agent as an interactive command-line chat
├── server_fun.py     # MCP tool server (weather, books, jokes, dogs, trivia)
├── index.html        # Chat UI
├── requirements.txt  # Python dependencies
└── .env.example      # Copy to .env and add your key
```

## How It Works

1. `app.py` starts `server_fun.py` as an MCP server and lists its tools.
2. Your request goes to the LLM with instructions to reply **only in JSON**: either `{"action": "<tool>", "args": {...}}` or `{"action": "final", "answer": "..."}`.
3. Each tool call runs on the MCP server, and the result goes back to the LLM as an *Observation*.
4. Bad JSON, unknown tools and tool errors are fed back so the model can correct itself.
5. After at most 10 steps, the final itinerary is shown in the chat, with the dog photo displayed inline.

---

## What's New

**New feature**
- The agent now uses the **trivia** tool: itineraries include a multiple-choice trivia question, with the answer revealed at the end.

**Fixes**
- Dog photos and links no longer break when the AI puts punctuation right after the URL (e.g. `….jpg.` or `(….jpg)`), and markdown links such as `![dog](url)` display correctly.
- Replies keep their line breaks and show `**bold**` text as bold.
- The send button is disabled while the Wizard is working, so a request can't be sent twice.
- Failed tool calls are logged as failures in the server console (previously they were logged as "success").

---

*AI Level 2 Training Project*
