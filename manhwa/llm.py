"""Le modèle de langage : GPT-4.1 via le proxy compatible OpenAI, ou Claude (Anthropic) en secours.

Réglé dans .env :
    DAILY_OPENAI_BASE_URL   adresse du proxy (jusqu'à /v1)
    DAILY_OPENAI_MODEL      gpt-4.1
    DAILY_OPENAI_KEY        la clé (elle change chaque jour : se colle aussi depuis le Studio)
    ANTHROPIC_API_KEY       une clé Claude (console.anthropic.com) : prise quand la clé GPT manque ou
                            est refusée (expirée). Modèle : CLAUDE_MODEL, claude-haiku-5-5 par défaut.

Les clés ne sont jamais écrites ailleurs que dans .env (ignoré par git) ni renvoyées au navigateur.
"""
import json
import os
import re
import time

import requests

from manhwa.config import ROOT, load_env

ENV_KEYS = ("DAILY_OPENAI_BASE_URL", "DAILY_OPENAI_MODEL", "DAILY_OPENAI_KEY", "ANTHROPIC_API_KEY", "CLAUDE_MODEL")
DEFAULT_MODEL = "gpt-4.1"
CLAUDE_MODEL = "claude-haiku-5-5"  # rapide et peu cher : relire, choisir, décrire
CLAUDE_URL = "https://api.anthropic.com"  # explicite : jamais une adresse héritée de l'environnement


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
        "claude_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "claude_model": os.environ.get("CLAUDE_MODEL") or CLAUDE_MODEL,
    }


def _hint(key):
    return f"{key[:3]}…{key[-4:]}" if len(key) > 8 else ("…" if key else "")


def public_settings():
    """Ce que le Studio peut afficher : jamais la clé entière."""
    s = settings()
    gpt = bool(s["base"] and s["key"])
    return {"configured": gpt or bool(s["claude_key"]), "gpt_configured": gpt, "base": s["base"], "model": s["model"],
            "key_hint": _hint(s["key"]), "claude": {"configured": bool(s["claude_key"]), "model": s["claude_model"],
                                                     "key_hint": _hint(s["claude_key"])}}


def save_settings(base=None, model=None, key=None, claude_key=None):
    """Met à jour .env (les autres lignes sont gardées) et l'environnement du serveur."""
    path = env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else [
        "# Jamais commité (.gitignore). Se change aussi depuis le Studio : Réglages → Clé GPT."]
    values = {"DAILY_OPENAI_BASE_URL": normalize_base(base) if base is not None else None,
              "DAILY_OPENAI_MODEL": model.strip() if model else None,
              "DAILY_OPENAI_KEY": key.strip() if key else None,
              "ANTHROPIC_API_KEY": claude_key.strip() if claude_key else None}
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
    """Un appel au modèle ; renvoie le texte (ou le JSON décodé si json_mode).

    GPT d'abord ; s'il n'a pas de clé, ou si elle est refusée (expirée), Claude prend le relais.
    """
    s = settings()
    if not (s["base"] and s["key"]):
        if s["claude_key"]:
            return _claude(messages, json_mode, max_tokens, timeout)
        raise LLMError("Clé GPT absente : colle-la dans le Studio (Réglages) ou dans .env")
    try:
        return _gpt(s, messages, json_mode, temperature, max_tokens, timeout)
    except LLMError as e:
        if s["claude_key"] and "refusée" in str(e):
            return _claude(messages, json_mode, max_tokens, timeout)
        raise


def _decode(content):
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)  # au cas où le modèle entoure le JSON de texte
        if m:
            return json.loads(m.group())
        raise


def _claude(messages, json_mode, max_tokens, timeout):
    """Le même appel, à Claude (bibliothèque officielle anthropic). Haiku 5.5 refuse temperature : on n'en met pas."""
    import anthropic

    s = settings()
    system = [str(m["content"]) for m in messages if m.get("role") == "system"]
    if json_mode:
        system.append("Answer only with valid JSON, no text around it.")
    turns = []
    for m in messages:
        if m.get("role") == "system":
            continue
        content = m["content"]
        if isinstance(content, list):  # texte et images (vision.py) : au format Anthropic
            blocks = []
            for part in content:
                if part.get("type") == "text":
                    blocks.append({"type": "text", "text": part["text"]})
                elif part.get("type") == "image_url":
                    head, _, data = part["image_url"]["url"].partition(",")
                    blocks.append({"type": "image", "source": {"type": "base64", "data": data,
                                                               "media_type": head.removeprefix("data:").split(";")[0]}})
            content = blocks
        turns.append({"role": m.get("role", "user"), "content": content})
    client = anthropic.Anthropic(api_key=s["claude_key"], base_url=os.environ.get("CLAUDE_BASE_URL") or CLAUDE_URL,
                                 timeout=timeout, max_retries=3)
    try:
        r = client.messages.create(model=s["claude_model"], max_tokens=max_tokens + 8000,  # la réflexion compte aussi
                                   system="\n\n".join(system) or anthropic.NOT_GIVEN, messages=turns,
                                   output_config={"effort": "low"})
    except anthropic.AuthenticationError:
        raise LLMError("Clé Claude refusée : vérifie-la dans le Studio (Réglages)")
    except anthropic.APIError as e:
        raise LLMError(f"Claude injoignable : {str(e)[:200]}")
    if r.stop_reason == "refusal":
        raise LLMError("Claude a refusé de répondre")
    text = "".join(b.text for b in r.content if b.type == "text")
    if not json_mode:
        return text
    try:
        return _decode(text)
    except json.JSONDecodeError:
        raise LLMError("Claude : réponse qui n'est pas du JSON")


def _gpt(s, messages, json_mode, temperature, max_tokens, timeout):
    body = {"model": s["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
        if not any("json" in str(m.get("content", "")).lower() for m in messages):
            # Azure (derrière le proxy) refuse une réponse JSON si le mot « json » n'apparaît nulle part
            body["messages"] = [{"role": "system", "content": "Answer only with JSON."}] + list(messages)
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
            return _decode(content)
        except json.JSONDecodeError:
            last = "réponse qui n'est pas du JSON"
    raise LLMError(f"GPT injoignable : {last}")


def ping():
    return chat([{"role": "user", "content": 'Reply with this JSON: {"ok": true}'}], max_tokens=20).get("ok") is True
