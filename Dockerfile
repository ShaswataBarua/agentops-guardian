# Hugging Face Spaces (Docker SDK) runs this on port 7860 as a non-root user.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    AGENTOPS_DB=/tmp/agentops.db \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
EXPOSE 7860
# The free Space's disk is wiped on restart, so re-seed the demo history every start.
CMD ["sh", "-c", "python seed_demo.py && uvicorn api:app --host 0.0.0.0 --port 7860"]
