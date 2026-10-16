"""Pilote automatique : ce que la machine décide seule, réglé dans config.toml → [auto].

    sounds   = true   le son proposé d'après l'image va dans la vidéo tant que tu ne choisis pas
    review   = true   pendant « Tout faire », les corrections de GPT (texte, type, qui parle) sont
                      acceptées d'office (« Relire » lancé à la main te laisse décider)
    speakers = 0.0    « qui parle » validé d'office à partir de cette confiance (0 = jamais ;
                      banc du ch. 1 : à 0,2, 37 % des répliques validées, dont 79 % justes)

Tout ce qui est décidé d'office reste visible (« d'office » dans le Studio) et se change
comme le reste ; un choix fait à la main n'est jamais remplacé.
"""


def settings(cfg):
    auto = (cfg or {}).get("auto") or {}
    return {"sounds": bool(auto.get("sounds", True)), "review": bool(auto.get("review", True)),
            "speakers": float(auto.get("speakers", 0.0) or 0.0)}


def accept_review(data):
    """Accepte d'office les propositions de GPT encore en attente (marquées « auto »)."""
    from manhwa.review import decide

    decisions = []
    for frame in data["frames"]:
        for j, b in enumerate(frame.get("bubbles") or []):
            r = (frame.get("review") or {}).get(b["text"]) or {}
            for field, state in (r.get("state") or {}).items():
                if state == "pending" and r.get("by") != "local":
                    decisions.append({"key": f"{frame['file']}#{j}", "field": field, "state": "accepted", "_auto": True})
                    r.setdefault("auto", [])
                    if field not in r["auto"]:
                        r["auto"].append(field)
    return decide(data, decisions)


def validate_speakers(data, crew, threshold):
    """Valide d'office « qui parle » quand la proposition est assez sûre."""
    from manhwa.cast import lines

    if threshold <= 0:
        return 0
    frames = {f["file"]: f for f in data["frames"]}
    n = 0
    for line in lines(data, crew):
        if line["speaker"] or not line["suggestion"] or line["confidence"] < threshold:
            continue
        frame = frames[line["frame"]]
        orig = frame["bubbles"][int(line["key"].split("#")[1])]["text"]
        frame.setdefault("speakers", {})[orig] = line["suggestion"]
        auto = frame.setdefault("speakers_auto", [])
        if orig not in auto:
            auto.append(orig)
        n += 1
    return n


def run_pilot(chapter, cfg, progress=None):
    """L'étape « pilote » de Tout faire : qui parle d'office (le reste se décide à sa place)."""
    from manhwa.cast import load_cast

    s = settings(cfg)
    data = chapter.load()
    n = validate_speakers(data, load_cast(chapter), s["speakers"])
    if s["review"]:
        n += accept_review(data)
    chapter.save(data)
    print(f"  Pilote : {n} décisions prises d'office.")
    return n


def summary(chapter, data, cfg):
    """Ce que la machine a décidé seule sur ce chapitre (affiché dans l'onglet Vidéo)."""
    from manhwa import sfx
    from manhwa.scene import load_scene

    texts = kinds = 0
    for frame in data["frames"]:
        for r in (frame.get("review") or {}).values():
            st = r.get("state") or {}
            auto = r.get("auto") or []
            local = r.get("by") == "local"
            texts += st.get("text") == "accepted" and ("text" in auto or local)
            kinds += st.get("kind") == "accepted" and ("kind" in auto or local)
    speakers = sum(len(f.get("speakers_auto") or []) for f in data["frames"])
    sounds = 0
    if settings(cfg)["sounds"]:
        seen = load_scene(chapter)
        sounds = sum(1 for s in sfx.spots(data, seen) + sfx.silent_frames(data, seen) if not s["chosen"] and s["proposed"] != sfx.NONE)
    return {"textes": texts, "types": kinds, "qui parle": speakers, "sons": sounds}
