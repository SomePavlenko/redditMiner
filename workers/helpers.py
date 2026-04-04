import json
import os
import re
import logging
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
import anthropic

ROOT = os.path.join(os.path.dirname(__file__), "..")

_env_loaded = False
_client = None


def load_config():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)


def save_config(config):
    with open(os.path.join(ROOT, "config.json"), "w") as f:
        json.dump(config, f, indent=2)


def load_env():
    global _env_loaded
    if not _env_loaded:
        load_dotenv(os.path.join(ROOT, ".env"))
        _env_loaded = True


def _get_client():
    global _client
    if _client is None:
        load_env()
        _client = anthropic.Anthropic()
    return _client


def setup_logger(worker_name):
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    log_file = os.path.join(
        ROOT, "logs", f"{worker_name}_{datetime.now().strftime('%Y%m%d')}.log"
    )
    logger = logging.getLogger(worker_name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(sh)
    return logger


def parse_json_response(raw, logger):
    """Safely parse JSON from Claude response, stripping markdown fences."""
    raw = raw.strip()
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if match:
        raw = match.group(1).strip()
    return json.loads(raw)


def claude_call(model, prompt, config, logger, max_tokens=8192):
    client = _get_client()
    for attempt in range(config["claude_retry_attempts"]):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                timeout=180.0,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"Claude API attempt {attempt+1} failed: {e}")
            if attempt < config["claude_retry_attempts"] - 1:
                time.sleep(config["claude_retry_backoff_seconds"] * (attempt + 1))
            else:
                raise
