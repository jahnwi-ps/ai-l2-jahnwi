import json, os, sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import AsyncExitStack, asynccontextmanager
from pydantic import BaseModel, Field
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Config ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    sys.exit("Error: GROQ_API_KEY missing. Copy .env.example to .env and set your key.")

client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
MODEL = os.getenv("MODEL", "llama-3.3-70b-versatile")
MAX_STEPS = 10

SYSTEM = (
    "You are the Weekend Wizard, a helpful AI agent.\n"
    "You solve requests step-by-step using tools. DO NOT skip tools or make up data.\n\n"
    "YOUR TOOLS:\n"
    "1. city_to_coords(city: str) -> Get lat/long for a city name.\n"
    "2. get_weather(latitude: float, longitude: float) -> Get current weather.\n"
    "3. book_recs(topic: str) -> Get book suggestions.\n"
    "4. random_joke() -> Get a joke.\n"
    "5. random_dog() -> Get a dog image URL.\n"
    "6. trivia() -> Get a multiple-choice trivia question.\n\n"
    "PROCESS:\n"
    "1. THOUGHT: What information is missing? Which tool should I call?\n"
    "2. ACTION: Output ONLY the JSON for that tool.\n"
    "3. OBSERVE: Read the result from the tool.\n"
    "4. REPEAT until you have ALL info (Weather, Books, Joke, Trivia, Dog Link).\n"
    "5. FINAL: Output the itinerary including the REAL Dog URL and REAL weather data, plus the trivia "
    "question with its options (reveal the answer at the end).\n\n"
    "RULES:\n"
    "- Output ONLY raw JSON: {\"action\": \"...\", \"args\": {...}} or {\"action\": \"final\", \"answer\": \"...\"}\n"
    "- If you have the weather, move on to the next tool. DON'T repeat tools.\n"
    "- You MUST include the Dog URL in your final answer."
)

# --- MCP Connection ---
class WizardBrain:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.session = None
        self.tool_names = set()

    async def connect(self):
        # Use the same interpreter and an absolute path so this works from any cwd / venv
        server_params = StdioServerParameters(command=sys.executable, args=[str(BASE_DIR / "server_fun.py")])
        stdio = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self.exit_stack.enter_async_context(ClientSession(stdio[0], stdio[1]))
        await self.session.initialize()
        self.tool_names = {t.name for t in (await self.session.list_tools()).tools}

    async def close(self):
        await self.exit_stack.aclose()

    async def chat(self, user_input: str) -> str:
        print(f"  [Wizard starts thinking about: {user_input}]")
        try:
            history = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_input}]

            for _ in range(MAX_STEPS):
                response = await client.chat.completions.create(
                    model=MODEL, messages=history, temperature=0.1, response_format={"type": "json_object"}
                )
                raw = response.choices[0].message.content
                # Keep the model's own decisions in context so it knows which tools it already called
                history.append({"role": "assistant", "content": raw})
                try:
                    decision = json.loads(raw)
                except json.JSONDecodeError:
                    history.append({"role": "user", "content": "Error: your reply was not valid JSON. Retry."})
                    continue

                if decision.get("action") == "final":
                    print("  [Wizard finished successfully]")
                    return str(decision.get("answer") or "")

                tname = decision.get("action")
                args = decision.get("args") or {}
                if tname not in self.tool_names:
                    history.append({"role": "user", "content": f"Error: Tool '{tname}' not found. Use one of: {sorted(self.tool_names)}"})
                    continue
                if not isinstance(args, dict):
                    history.append({"role": "user", "content": "Error: 'args' must be a JSON object. Retry."})
                    continue

                print(f"  [Web Wizard calls {tname} with {args}]")
                try:
                    result = await self.session.call_tool(tname, args)
                    payload = result.content[0].text if result.content else str(result)
                    # A tool that raises comes back as isError=True rather than an exception
                    print(f"  [Tool {tname} {'failed: ' + payload if result.isError else 'success'}]")
                    history.append({"role": "user", "content": f"Observation: {payload}"})
                except Exception as e:
                    print(f"  [Tool Error in {tname}: {e}]")
                    history.append({"role": "user", "content": f"Tool Error: {e}"})

            return "The Wizard ran out of steps before finishing. Please try a simpler request."
        except Exception as e:
            print(f"  [CRITICAL ERROR]: {e}")
            return "Sorry, something went wrong while planning. Please try again."

wizard = WizardBrain()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await wizard.connect()
    yield
    await wizard.close()

app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    response_text = await wizard.chat(req.message)
    return JSONResponse({"reply": response_text})

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return (BASE_DIR / "index.html").read_text(encoding="utf-8")

if __name__ == "__main__":
    import uvicorn
    # Localhost by default; set HOST=0.0.0.0 to expose on your network
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
