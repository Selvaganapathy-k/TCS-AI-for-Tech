import requests, json, re
from .config import OLLAMA_BASE_URL, OLLAMA_MODEL

def available():
    try: return requests.get(OLLAMA_BASE_URL + "/api/tags", timeout=2).ok
    except requests.RequestException: return False

def ask(prompt, system="You are a careful software architecture engineer. Use only supplied evidence."):
    r = requests.post(OLLAMA_BASE_URL + "/api/chat", json={
        "model":OLLAMA_MODEL, "stream":False,
        "messages":[{"role":"system","content":system},{"role":"user","content":prompt}],
        "options":{"temperature":0.1}
    }, timeout=180)
    r.raise_for_status()
    return r.json()["message"]["content"]

def json_from(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try: return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]|\{.*\}", text, re.S)
        if not m: raise
        return json.loads(m.group(0))
