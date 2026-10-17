import asyncio, json, sys, os
from typing import Dict, Any, List
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("Error: GROQ_API_KEY missing. Copy .env.example to .env and set your key.")
    sys.exit(1)

client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
MODEL = "llama-3.3-70b-versatile" 

SYSTEM = (
    "You are the Weekend Wizard. You must follow the ReAct pattern exactly.\n\n"
    "TOOLS AVAILABLE:\n"
    "- city_to_coords(city: str)\n"
    "- get_weather(latitude: float, longitude: float)\n"
    "- book_recs(topic: str)\n"
    "- random_joke()\n"
    "- random_dog()\n\n"
    "RESPONSE FORMAT (JSON ONLY):\n"
    "To call a tool:\n"
    "{\"action\": \"tool_name\", \"args\": {\"arg_name\": \"value\"}}\n\n"
    "To finish:\n"
    "{\"action\": \"final\", \"answer\": \"your full upbeat itinerary\"}\n\n"
    "CRITICAL: Always put the tool name in the 'action' field. Do not use 'tool' or 'method'. Only 'action'."
)

def llm_json(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0, # Maximum precision
        response_format={ "type": "json_object" }
    )
    raw = response.choices[0].message.content
    # Keep the model's own decisions in context so it knows which tools it already called
    messages.append({"role": "assistant", "content": raw})
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "final", "answer": "I had trouble formatting my thoughts. Please try again."}

async def main():
    server_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_fun.py")
    exit_stack = AsyncExitStack()
    try:
        stdio = await exit_stack.enter_async_context(
            stdio_client(StdioServerParameters(command=sys.executable, args=[server_path]))
        )
        session = await exit_stack.enter_async_context(ClientSession(stdio[0], stdio[1]))
        await session.initialize()

        tools = (await session.list_tools()).tools
        tool_index = {t.name: t for t in tools}
        
        print("\n--- 🪄 Weekend Wizard CLI Active ---")
        history = [{"role": "system", "content": SYSTEM}]
        
        while True:
            user_input = input("\nYou: ").strip()
            if not user_input or user_input.lower() in {"exit", "quit"}: break
            history.append({"role": "user", "content": user_input})

            for i in range(10):
                decision = llm_json(history)
                
                # Robust extraction of the action
                tname = decision.get("action") or decision.get("tool") or decision.get("call")
                args = decision.get("args", {})
                
                if tname == "final":
                    print(f"\nWizard: {decision.get('answer')}")
                    break
                
                if not tname:
                    history.append({"role": "user", "content": "Error: You forgot to specify an 'action' in your JSON. Please retry the tool call."})
                    continue

                if tname not in tool_index:
                    history.append({"role": "user", "content": f"Error: Tool '{tname}' not found. Use: {list(tool_index.keys())}"})
                    continue

                # Auto-correction for argument format (Llama sometimes sends lists instead of strings)
                if isinstance(args, list) and len(args) > 0 and tname == "city_to_coords":
                    args = {"city": args[0]}

                print(f"  [Step {i+1}: Calling {tname} with {args}]")
                try:
                    result = await session.call_tool(tname, args)
                    payload = result.content[0].text if (hasattr(result, 'content') and result.content) else str(result)
                    history.append({"role": "user", "content": f"Observation: {payload}"})
                except Exception as e:
                    history.append({"role": "user", "content": f"Tool Error: {e}. Please try a different approach."})
                
    finally:
        await exit_stack.aclose()

if __name__ == "__main__":
    asyncio.run(main())
