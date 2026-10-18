# Deploy for free on Hugging Face Spaces (about 15 minutes)

You get a public link like `https://YOUR_HF_USERNAME-agentops-breaker.hf.space` that judges can open with no login.
No credit card needed.

## Steps

1. Sign in at huggingface.co. Click your avatar, then **New Space**.
2. Name: `agentops-breaker`. SDK: **Docker** (choose "Blank"). Hardware: **CPU basic (free)**. Visibility: **Public**. Click **Create Space**.
3. In the Space, open the **Files** tab, then **Add file, Upload files**. Drag in everything from your project folder:
   all `.py` files, `dashboard.html`, `requirements.txt`, `Dockerfile`, `.dockerignore`, `README.md`, and the `eval/` and `deploy/` folders.
   **Do NOT upload:** `.env`, `.venv/`, `*.db`, `__pycache__/`. The Space is public: anything you upload is public.
   (The `tests/` folder is optional; the Dockerfile ignores it.)
4. Open `README.md` in the Space, click Edit, and paste the contents of `deploy/space_readme_header.txt` at the very top
   (the lines between the two `---`), above the existing text. Spaces will not build without that header. Commit.
5. The Space starts **Building**, then **Running** (2 to 5 minutes). Watch the **Logs** if it fails and send me the last 20 lines.
6. Open the **App** tab. You should see the dashboard with two agents already listed (`demo-support-bot`, `demo-rogue-bot`).
7. Test like a judge: open the link in a private browser window on your phone (mobile data, not your Wi-Fi), run one script of each kind,
   approve one action, and open `/docs`.

## Things to know before you rely on it

- **Data resets** whenever the Space restarts (the free disk is temporary). `seed_demo.py` refills the two example agents; runs you made are gone.
  The seeded history is labelled `(demo seed)` so nobody mistakes it for real agent behaviour.
- **Free Spaces go to sleep** when nobody visits for a while. Open the link 10 minutes before you present so it is awake.
- **Anyone with the link can use the dashboard**, including the approve and kill buttons. Fine for a demo; do not put real data in it.
- **Gemini key:** only add `GEMINI_API_KEY` (Settings, Variables and secrets, New secret) if you want the real-LLM scenario on the public link.
  Anyone could then trigger runs that spend your free quota, and free-tier limits change. Safer: leave it out of the public Space,
  record the Gemini run as a short video, and keep the live demo on the scripted scenarios.
- **Telemetry:** to send traces from the Space to a collector, add `OTEL_EXPORTER_OTLP_ENDPOINT` as a secret. Leave it unset otherwise.
- **MCP:** point the MCP server at the public link with `AGENTOPS_URL=https://YOUR_HF_USERNAME-agentops-breaker.hf.space python mcp_server.py`.
- **Not verified here:** I could not run Docker in my environment, so the Dockerfile build is untested. The start command
  (seed, then uvicorn on port 7860) was tested locally and works. If the build fails, check Hugging Face's "Docker Spaces" docs for
  current requirements and send me the log.
