"""Skin profile -> product recommendations, plus optional photo analysis via Claude vision.

Privacy: images are only ever held in memory for the duration of one request. They are never
written to disk or logged. Analysis is cosmetic/informational, never a medical diagnosis.
"""
import base64, json, math, os, random, re, ssl, urllib.request
from . import glossary


def _ssl_ctx():
    """Verified TLS context. python.org builds on macOS ship without CA certs, so fall back to system bundles."""
    try:
        import certifi; return ssl.create_default_context(cafile=certifi.where())
    except ImportError: pass
    for f in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if os.path.exists(f): return ssl.create_default_context(cafile=f)
    return ssl.create_default_context()

SKIN_TYPES = ("oily", "dry", "combination", "normal")
# concern -> ingredient keywords commonly associated with it (cosmetic, not medical, claims)
CONCERNS = {
    "acne_blemishes": ["salicylic", "niacinamide", "zinc", "azelaic", "benzoyl", "tea tree"],
    "redness_sensitivity": ["centella", "panthenol", "allantoin", "ceramide", "colloidal oat", "bisabolol"],
    "dark_spots": ["vitamin c", "ascorb", "niacinamide", "tranexamic", "arbutin", "azelaic"],
    "fine_lines": ["retinol", "retinal", "peptide", "bakuchiol"],
    "dullness": ["vitamin c", "ascorb", "glycolic", "lactic acid", "mandelic"],
    "dehydration": ["hyaluronic", "glycerin", "ceramide", "squalane", "panthenol"],
    "oiliness_pores": ["niacinamide", "salicylic", "zinc", "clay", "kaolin"],
}
TYPE_DEFAULTS = {"oily": ["oiliness_pores"], "dry": ["dehydration"], "combination": ["oiliness_pores", "dehydration"],
                 "normal": ["dehydration"]}
FRAGRANCE = ("fragrance", "parfum", "limonene", "linalool")
AVOID = {"fragrance": ("fragrance", "parfum", "limonene", "linalool"), "alcohol": ("alcohol denat", "sd alcohol", "ethanol"),
         "essential oils": ("essential oil", "lavandula", "mentha", "citrus", "eucalyptus", "peppermint")}
BAD_SUBCATS = ("Value & Gift Sets", "Mini Size", "High Tech Tools", "Wellness", "Self Tanners", "Shop by Concern")


def normalise(profile):
    t = (profile.get("skin_type") or "").lower()
    t = t if t in SKIN_TYPES else None
    cs = [c for c in profile.get("concerns", []) if c in CONCERNS]
    avoid = [x for x in profile.get("avoid", []) if x in AVOID]
    wt = {c: float(v) for c, v in (profile.get("weights") or {}).items() if c in CONCERNS}
    return {"skin_type": t, "concerns": cs, "avoid": avoid, "weights": wt, "sensitive": bool(profile.get("sensitive") or "redness_sensitivity" in cs or "fragrance" in avoid)}


def recommend(con, profile, k=6, salt=None):
    p = normalise(profile)
    concerns = p["concerns"] or TYPE_DEFAULTS.get(p["skin_type"], ["dehydration"])
    kws = {kw for c in concerns for kw in CONCERNS[c]}
    marks = ",".join("?" * len(BAD_SUBCATS))
    hits = {}
    for kw in kws:
        for pid in con.execute(f"""SELECT DISTINCT p.product_id FROM products p JOIN ingredients i USING(product_id)
            WHERE p.category='Skincare' AND p.subcategory NOT IN ({marks}) AND p.rating>=4 AND p.n_reviews>=50
            AND i.ingredient LIKE ?""", (*BAD_SUBCATS, f"%{kw}%")):
            hits.setdefault(pid[0], set()).add(kw)
    scored = []
    for pid, kw in sorted(hits.items(), key=lambda x: -len(x[1]))[:80]:
        name, brand, price, rating, nrev, sub = con.execute(
            "SELECT name,brand,price_usd,rating,n_reviews,subcategory FROM products WHERE product_id=?", (pid,)).fetchone()
        ings = [r[0].lower() for r in con.execute("SELECT ingredient FROM ingredients WHERE product_id=?", (pid,))]
        fragranced = any(f in i for i in ings for f in FRAGRANCE[:2])
        if p["sensitive"] and fragranced: continue
        if any(w in i for x in p["avoid"] for w in AVOID[x] for i in ings): continue
        if p["sensitive"] and any(w in i for w in ("retinol", "retinal", "retinyl", "retinoic") for i in ings): continue   # too strong for reactive skin
        if (name or "").lower().startswith("mini "): continue
        rate, n = None, 0
        if p["skin_type"]:
            r = con.execute("SELECT AVG(recommended),COUNT(*) FROM reviews WHERE product_id=? AND skin_type=?", (pid, p["skin_type"])).fetchone()
            rate, n = r[0], r[1]
        cover = sum(p["weights"].get(c, 3 if c in p["concerns"] else 1) * len(set(CONCERNS[c]) & kw) for c in concerns)   # severity-weighted
        score = 1.5 * cover + (rating - 4) + (2 * rate if rate is not None and n >= 10 else 0) + min(math.log10(max(nrev, 1)), 4) * 0.15
        why = ["Contains " + ", ".join(f"{k} ({glossary.short(k) or 'skin-conditioning'})" for k in sorted(kw))]
        if rate is not None and n >= 10: why.append(f"{round(rate*100)}% of {n} reviewers with {p['skin_type']} skin recommend it")
        scored.append((score, dict(id=pid, name=name, brand=brand, price=price, rating=round(rating, 1), reviews=nrev,
                                   type=sub, why=why, fragrance=fragranced)))
    # pick from the strongest candidates with a weighted draw, so similar profiles are not all given the identical list.
    # The draw is seeded by the profile + this visitor's salt: stable for one person, different between people.
    rng = random.Random(f"{salt}|{p['skin_type']}|{sorted(concerns)}|{sorted(p['avoid'])}")
    pool = sorted(scored, key=lambda x: -x[0])[:30]
    out, seen = [], {}
    while pool and len(out) < k:
        top = pool[0][0]
        wts = [math.exp((sc - top) / 2.5) for sc, _ in pool]
        i = rng.choices(range(len(pool)), weights=wts)[0]
        _, d = pool.pop(i)
        if seen.get(d["type"], 0) >= 2 or any(d["name"].lower().replace("mini ", "") == o["name"].lower() for o in out): continue
        out.append(d); seen[d["type"]] = seen.get(d["type"], 0) + 1
    from collections import Counter
    top = Counter(k for d in out for k in re.findall(r"(?:Contains |, )([a-z][a-z ]+?) \(", d["why"][0]) if glossary.find_ingredient(k))
    return {"profile": p, "focus": concerns, "products": out, "top_ingredients": [glossary.find_ingredient(k) for k, _ in top.most_common(2)]}


PROMPT = """You are a cosmetic beauty assistant doing a visual check of a photo, like the first look in a consultation.
Describe ONLY visible, cosmetic characteristics. Do NOT diagnose any medical condition or name diseases.
Rate each area from the photo as "none", "mild", "moderate" or "notable". Reply with JSON only:
{"usable": bool (false if no clearly visible skin AND no visible hair, or the photo is too dark or blurry),
 "findings": {"texture_pores": "..", "blemishes": "..", "pigmentation": "..", "redness": "..", "fine_lines": "..", "dryness": "..", "oiliness": ".."},
 "skin_type": "oily|dry|combination|normal|unclear",
 "skin_tone": "fair|light|medium|tan|deep|unclear",
 "undertone": "warm|cool|neutral|olive|unclear",
 "temporary": subset of ["dehydration","irritation"] (short-term states, not the natural skin type),
 "hair": {"visible": bool, "texture": "straight|wavy|curly|coily|unclear", "frizz": "none|mild|moderate|notable",
          "dryness": "none|mild|moderate|notable", "damage": "none|mild|moderate|notable"},
 "observations": [up to 4 short plain-language notes of what is visible],
 "unusual_spot": true only if a spot or mark looks unusual enough that an in-person check would be sensible, else false,
 "confidence": "low|medium|high"}
Photos cannot reliably show skin type or undertone; be conservative and prefer "unclear"/low confidence when unsure."""


LOCAL_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LOCAL_MODEL = os.environ.get("LOCAL_VISION_MODEL", "qwen2.5vl:7b")
LOCAL_NAME = "a local model on this computer"


def _local_ready():
    try:
        with urllib.request.urlopen(LOCAL_URL + "/api/tags", timeout=1) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
        return any(n == LOCAL_MODEL or n.split(":")[0] == LOCAL_MODEL.split(":")[0] and ":" not in LOCAL_MODEL for n in names)
    except Exception:
        return False


def provider():
    """Photo analysis backend. Local model is preferred and is the default; cloud APIs are used only if
    ALLOW_CLOUD_VISION=1 is set explicitly, so a photo never leaves this machine by surprise."""
    if _local_ready(): return LOCAL_NAME
    if os.environ.get("ALLOW_CLOUD_VISION") == "1":
        if os.environ.get("OPENAI_API_KEY"): return "OpenAI"
        if os.environ.get("ANTHROPIC_API_KEY"): return "Anthropic"
    return None


def _analyze_local(b64):
    body = json.dumps({"model": LOCAL_MODEL, "stream": False, "format": "json", "options": {"temperature": 0},
                       "messages": [{"role": "user", "content": PROMPT, "images": [b64]}]}).encode()
    req = urllib.request.Request(LOCAL_URL + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:   # localhost only; first call may be slow while the model loads
        return json.load(r)["message"]["content"]


def _analyze_openai(b64, media_type, model):
    body = json.dumps({"model": model, "max_tokens": 600, "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}", "detail": "low"}}]}]}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body, headers={
        "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx()) as r: resp = json.load(r)
    return resp["choices"][0]["message"]["content"] or ""


LEVEL = {"none": 0, "mild": 1, "moderate": 2, "notable": 3}
AREA = {"blemishes": "acne_blemishes", "redness": "redness_sensitivity", "pigmentation": "dark_spots",
        "fine_lines": "fine_lines", "dryness": "dehydration", "oiliness": "oiliness_pores", "texture_pores": "oiliness_pores"}


def derive(a):
    """Turn the visual findings into skincare concerns (cosmetic, not diagnostic)."""
    f = a.get("findings") or {}
    cs = [c for c in a.get("concerns", []) if c in CONCERNS]
    for area, c in AREA.items():
        if LEVEL.get(str(f.get(area, "none")).lower(), 0) >= 2 and c not in cs: cs.append(c)
    for t in a.get("temporary", []) or []:
        c = {"dehydration": "dehydration", "irritation": "redness_sensitivity"}.get(t)
        if c and c not in cs: cs.append(c)
    w = {}
    for area, c in AREA.items():
        lv = LEVEL.get(str(f.get(area, "none")).lower(), 0)
        if lv: w[c] = max(w.get(c, 0), lv)
    for c in cs: w.setdefault(c, 2)
    a["concerns"] = cs; a["weights"] = w
    return a


def clean(a):
    """Coerce whatever the model returned into the expected shape (small models often bend the schema)."""
    if not isinstance(a, dict): return {"usable": False, "findings": {}, "skin_type": "unclear", "temporary": [], "observations": [], "confidence": "low"}
    f = a.get("findings") if isinstance(a.get("findings"), dict) else {}
    fx = {}
    for k in ("texture_pores", "blemishes", "pigmentation", "redness", "fine_lines", "dryness", "oiliness"):
        v = f.get(k, "none")
        v = "mild" if v is True else str(v).strip().lower()
        fx[k] = v if v in LEVEL else "none"
    st = next((x for x in SKIN_TYPES if x in str(a.get("skin_type", "")).lower()), "unclear")
    tmp = a.get("temporary"); tmp = [tmp] if isinstance(tmp, str) else (tmp if isinstance(tmp, list) else [])
    obs = a.get("observations"); obs = [obs] if isinstance(obs, str) else (obs if isinstance(obs, list) else [])
    conf = str(a.get("confidence", "low")).lower()
    tone = next((x for x in ("fair", "light", "medium", "tan", "deep") if x == str(a.get("skin_tone", "")).strip().lower()), None)
    under = next((x for x in ("warm", "cool", "neutral", "olive") if x == str(a.get("undertone", "")).strip().lower()), None)
    h = a.get("hair") if isinstance(a.get("hair"), dict) else {}
    hx = {"visible": h.get("visible") is True,
          "texture": next((x for x in ("straight", "wavy", "curly", "coily") if x == str(h.get("texture", "")).strip().lower()), None)}
    for k in ("frizz", "dryness", "damage"):
        v = str(h.get(k, "none")).strip().lower(); hx[k] = v if v in LEVEL else "none"
    return {"usable": a.get("usable", True) is not False, "findings": fx, "skin_type": st, "skin_tone": tone, "undertone": under, "hair": hx,
            "temporary": [t for t in map(str, tmp) if t in ("dehydration", "irritation")],
            "observations": [str(o)[:160] for o in obs][:4], "unusual_spot": a.get("unusual_spot") is True,
            "confidence": conf if conf in ("low", "medium", "high") else "low",
            "concerns": [c for c in (a.get("concerns") or []) if c in CONCERNS] if isinstance(a.get("concerns"), list) else []}


def analyze_image(b64, media_type, api_key=None, model="claude-sonnet-5-5"):
    last = None
    for _ in range(2):   # one retry: small local models occasionally return unusable JSON
        try: return derive(clean(_analyze_raw(b64, media_type, api_key, model)))
        except (ValueError, KeyError, TypeError, AttributeError) as e: last = e
    raise ValueError(f"unreadable analysis: {type(last).__name__}")


def _analyze_raw(b64, media_type, api_key=None, model="claude-sonnet-5-5"):
    if media_type not in ("image/jpeg", "image/png", "image/webp"): raise ValueError("Unsupported image type")
    prov = provider()
    if prov == LOCAL_NAME:
        text = _analyze_local(b64)
        m = re.search(r"\{.*\}", text, re.S)
        if not m: raise ValueError("Could not read the analysis")
        return json.loads(m.group(0))
    if prov is None and not api_key: raise RuntimeError("NO_KEY")
    if prov == "OpenAI" and not api_key:
        text = _analyze_openai(b64, media_type, os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
        m = re.search(r"\{.*\}", text, re.S)
        if not m: raise ValueError("Could not read the analysis")
        return json.loads(m.group(0))
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key: raise RuntimeError("NO_KEY")
    if media_type not in ("image/jpeg", "image/png", "image/webp"): raise ValueError("Unsupported image type")
    body = json.dumps({"model": model, "max_tokens": 600, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
        {"type": "text", "text": PROMPT}]}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx()) as r: resp = json.load(r)
    text = "".join(b.get("text", "") for b in resp.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    if not m: raise ValueError("Could not read the analysis")
    return json.loads(m.group(0))
