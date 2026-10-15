"""GPT-4.1 via le proxy compatible OpenAI (texte seulement), réglé dans .env.

    DAILY_OPENAI_BASE_URL   adresse du proxy (jusqu'à /v1)
    DAILY_OPENAI_MODEL      gpt-4.1
    DAILY_OPENAI_KEY        la clé (elle change chaque jour : se colle aussi depuis le Studio)

La clé n'est jamais écrite ailleurs que dans .env (ignoré par git) ni renvoyée au navigateur.
"""
import json
import os
import re
import time

import requests

from manhwa.config import ROOT, load_env

ENV_KEYS = ("DAILY_OPENAI_BASE_URL", "DAILY_OPENAI_MODEL", "DAILY_OPENAI_KEY")
DEFAULT_MODEL = "gpt-4.1"


class LLMError(RuntimeError):
    pass


def env_path():
    return ROOT / ".env"


def normalize_base(url):
    """« …/v1/chat/completions » ou « …/v1/ » → « …/v1 »."""
    url = (url or "").strip().rstrip("/")
    return re.sub(r"/chat/completions$", "", url)


def settings():
    load_env(env_path())
    return {
        "base": normalize_base(os.environ.get("DAILY_OPENAI_BASE_URL", "")),
        "model": os.environ.get("DAILY_OPENAI_MODEL") or DEFAULT_MODEL,
        "key": os.environ.get("DAILY_OPENAI_KEY", ""),
    }


def public_settings():
    """Ce que le Studio peut afficher : jamais la clé entière."""
    s = settings()
    key = s["key"]
    return {"configured": bool(s["base"] and key), "base": s["base"], "model": s["model"],
            "key_hint": f"{key[:3]}…{key[-4:]}" if len(key) > 8 else ("…" if key else "")}


def save_settings(base=None, model=None, key=None):
    """Met à jour .env (les autres lignes sont gardées) et l'environnement du serveur."""
    path = env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else [
        "# Jamais commité (.gitignore). Se change aussi depuis le Studio : Réglages → Clé GPT."]
    values = {"DAILY_OPENAI_BASE_URL": normalize_base(base) if base is not None else None,
              "DAILY_OPENAI_MODEL": model.strip() if model else None,
              "DAILY_OPENAI_KEY": key.strip() if key else None}
    seen = set()
    for i, line in enumerate(lines):
        name = line.split("=", 1)[0].strip()
        if name in values and values[name] is not None:
            lines[i] = f"{name}={values[name]}"
            seen.add(name)
    lines += [f"{n}={v}" for n, v in values.items() if v is not None and n not in seen]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    for name, value in values.items():
        if value is not None:
            os.environ[name] = value


def chat(messages, json_mode=True, temperature=0.2, max_tokens=4000, timeout=180):
    """Un appel au modèle ; renvoie le texte (ou le JSON décodé si json_mode)."""
    s = settings()
    if not (s["base"] and s["key"]):
        raise LLMError("Clé GPT absente : colle-la dans le Studio (Réglages) ou dans .env")
    body = {"model": s["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    last = None
    for attempt in range(4):
        try:
            r = requests.post(f"{s['base']}/chat/completions", json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {s['key']}"})
        except requests.RequestException as e:
            last = str(e)
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (401, 403):
            raise LLMError("Clé GPT refusée (expirée ?) : colle la nouvelle dans le Studio (Réglages)")
        if r.status_code == 429 or r.status_code >= 500:
            last = f"{r.status_code} {r.text[:200]}"
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise LLMError(f"GPT : erreur {r.status_code} {r.text[:200]}")
        content = r.json()["choices"][0]["message"]["content"] or ""
        if not json_mode:
            return content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.S)  # au cas où le modèle entoure le JSON de texte
            if m:
                return json.loads(m.group())
            last = "réponse qui n'est pas du JSON"
    raise LLMError(f"GPT injoignable : {last}")


def ping():
    return chat([{"role": "user", "content": 'Reply with {"ok": true}'}], max_tokens=20).get("ok") is True
