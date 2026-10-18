"""Run this ONCE on your machine to check the Gemini connection:  python llm_smoke.py"""
from dotenv import load_dotenv

load_dotenv()

from llm_agent import GeminiClient  # noqa: E402

client = GeminiClient()
print("model:", client.model)
out = client.step([{"role": "user", "parts": [{"text": "Look up order 1004 using the tool."}]}])
print(out)
if out["kind"] == "call" and out["name"] == "lookup_order" and out["args"].get("order_id") == 1004:
    print("OK: Gemini asked to call lookup_order(1004). The real agent will work.")
else:
    print("Gemini answered, but not with the expected tool call. Check the model name and try again.")
