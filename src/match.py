"""Recommendations beyond skincare: hair, makeup, fragrance and body care, plus one entry point for all of them.
Everything is matched on the catalogue's own tags / shade descriptions, then drawn with a weighted sample so
different people with similar answers are not all shown the identical list (stable per visitor)."""
import math, random, re
from . import skin as skinmod
from .catalogue import swatch

TITLES = {"skin": "Skincare picks for you", "hair": "Hair picks for you", "makeup": "Makeup that suits you",
          "fragrance": "Fragrances you might love", "body": "Body care picks"}

HAIR_TAGS = {"frizz": ("Good for: Frizz", "frizz"), "dryness": ("Good for: Dryness", "dryness"), "damage": ("Good for: Damage", "damage"),
             "color_care": ("Good for: Color Care", "colour-treated hair"), "volume": ("Good for: Volume", "volume"),
             "thinning": ("Good for: Hair Thinning", "thinning hair"), "dry_scalp": ("Good for: Flaky/Dry Scalp", "a dry scalp"),
             "oily_scalp": ("Good for: Oily Scalp", "an oily scalp"), "shine": ("Increases Shine", "shine")}
HAIR_TYPES = {"straight": "Straight Hair", "wavy": "Wavy Hair", "curly": "Curly Hair", "coily": "Coily Hair"}
HAIR_AVOID = {"sulfates": ("sulfate",), "silicones": ("dimethicone", "siloxane", "cyclomethicone", "silicone"), "fragrance": ("fragrance", "parfum")}

TONES = {"fair": ["fair", "pale", "porcelain", "very light", "ivory"], "light": ["light"], "medium": ["medium"],
         "tan": ["tan", "caramel", "golden"], "deep": ["deep", "dark", "rich", "ebony", "espresso"]}
UNDERTONES = {"warm": ["warm", "golden", "yellow", "peach"], "cool": ["cool", "pink", "rosy"], "neutral": ["neutral"], "olive": ["olive"]}
TONE_HEX = {"fair": "#f1d3bf", "light": "#e8bf9f", "medium": "#c99772", "tan": "#a8734d", "deep": "#6b4330"}
LIP = {"warm": ["coral", "orange", "brown", "red", "nude"], "cool": ["berry", "pink", "plum", "mauve", "red"],
       "neutral": ["mauve", "nude", "pink", "red", "coral"], "olive": ["wine", "brown", "coral", "berry", "red"]}
BLUSH = {"warm": ["coral", "orange", "pink"], "cool": ["pink", "berry", "mauve"], "neutral": ["pink", "coral", "mauve"], "olive": ["coral", "pink", "berry"]}
DEEP_LIP = ["wine", "berry", "plum", "brown", "red"]
LIGHT_LIP = ["pink", "coral", "nude", "mauve", "red"]

SCENTS = {"floral": ("Floral Scent", "floral"), "fresh": ("Fresh Scent", "fresh"), "woody": ("Woody & Earthy Scent", "woody"),
          "warm": ("Warm &Spicy Scent", "warm and spicy")}
BODY_TAGS = {"dryness": ("Good for: Dryness", "dry skin"), "dullness": ("Good for: Dullness/Uneven Texture", "dullness"),
             "firmness": ("Good for: Loss of firmness", "firmness")}


def _tags(h): return set(re.findall(r"'([^']+)'", h or ""))


def _draw(scored, k, rng, per=2, T=2.5):
    pool = sorted(scored, key=lambda x: -x[0])[:30]
    out, seen = [], {}
    while pool and len(out) < k:
        top = pool[0][0]
        i = rng.choices(range(len(pool)), weights=[math.exp((s - top) / T) for s, _ in pool])[0]
        _, d = pool.pop(i)
        if d["name"].lower().startswith("mini ") or seen.get(d["type"], 0) >= per or any(d["name"].lower() == o["name"].lower() for o in out): continue
        out.append(d); seen[d["type"]] = seen.get(d["type"], 0) + 1
    return out


def _card(r, why, sw=None):
    pid, name, brand, price, rating, nrev, sub, tert = r[:8]
    return dict(id=pid, name=name, brand=brand, price=price, rating=round(rating or 0, 1), reviews=nrev, type=tert or sub,
                shade="", shade_desc="", swatch=sw, why=[w for w in why if w])


def _has(con, pid, words):
    q = " OR ".join("lower(ingredient) LIKE ?" for _ in words)
    return con.execute(f"SELECT 1 FROM ingredients WHERE product_id=? AND ({q}) LIMIT 1", (pid, *[f"%{w}%" for w in words])).fetchone() is not None


def _rng(salt, *parts): return random.Random(f"{salt}|" + "|".join(map(str, parts)))


def _pop(nrev): return min(math.log10(max(nrev or 1, 1)), 4) * 0.15


# ---------------------------------------------------------------- hair
def hair(con, p, k=5, salt=None):
    htype = p.get("type") if p.get("type") in HAIR_TYPES else None
    cons = [c for c in p.get("concerns", []) if c in HAIR_TAGS]
    avoid = [a for a in p.get("avoid", []) if a in HAIR_AVOID]
    w = p.get("weights") or {}
    rows = con.execute("""SELECT product_id,name,brand,price_usd,rating,n_reviews,subcategory,tertiary,highlights FROM products
        WHERE category='Hair' AND subcategory IN ('Shampoo & Conditioner','Hair Styling & Treatments') AND n_reviews>=20 AND rating>=4""").fetchall()
    scored = []
    for r in rows:
        tags = _tags(r[8]); s, why = 0.0, []
        if htype:
            if HAIR_TYPES[htype] in tags: s += 3; why.append(f"Made for {htype} hair")
            elif "All Hair Types" in tags: s += 1; why.append("Suits all hair types")
            if htype in ("curly", "coily") and "Curl-Enhancing" in tags: s += 1.5; why.append("Curl-enhancing")
        for c in cons:
            if HAIR_TAGS[c][0] in tags: s += 1.2 * float(w.get(c, 3)); why.append(f"Good for {HAIR_TAGS[c][1]}")
        if (htype or cons) and s <= 0: continue
        if "sulfates" in avoid and "Without Sulfates SLS & SLES" in tags: s += 1; why.append("Sulfate-free")
        s += (r[4] - 4) + _pop(r[5])
        scored.append((s, _card(r, why)))
    scored.sort(key=lambda x: -x[0]); scored = scored[:60]
    if avoid:   # ingredient-level check on the strongest candidates
        scored = [(s, d) for s, d in scored if not any(_has(con, d["id"], HAIR_AVOID[a]) for a in avoid)]
    return _draw(scored, k, _rng(salt, "hair", htype, sorted(cons), sorted(avoid)))


# ---------------------------------------------------------------- makeup
def _hits(text, words): return sum(1 for x in words if re.search(r"\b" + re.escape(x), text))


def makeup(con, cat, p, k=6, salt=None, parts=("base", "lip", "cheek")):
    tone = p.get("tone") if p.get("tone") in TONES else None
    under = p.get("undertone") if p.get("undertone") in UNDERTONES else None
    finish = p.get("finish") if p.get("finish") in ("matte", "natural", "radiant") else None
    rng = _rng(salt, "makeup", tone, under, finish)
    out = []
    if tone and "base" in parts:   # base products whose shade description matches the skin tone / undertone
        rows = con.execute("""SELECT product_id,name,brand,price_usd,rating,n_reviews,subcategory,tertiary,highlights,shade,shade_desc FROM products
            WHERE tertiary IN ('Foundation','Concealer','Tinted Moisturizer','BB & CC Cream') AND n_reviews>=10 AND rating>=3.8""").fetchall()
        scored = []
        for r in rows:
            hay = f"{r[9] or ''} {r[10] or ''}".lower()
            th = _hits(hay, TONES[tone])
            if not th: continue
            uh = _hits(hay, UNDERTONES[under]) if under else 0
            if under and not uh and re.search(r"\b(warm|cool|neutral|olive|golden|pink)\b", hay): continue   # clearly a different undertone
            tags = _tags(r[8]); s = 3 * th + 2 * uh + (r[4] - 4) + _pop(r[5])
            if finish and f"{finish.title()} Finish" in tags: s += 1.5
            d = _card(r, [f"Shade: {r[9]}" if r[9] else "", f"Described as: {r[10]}" if r[10] else ""], TONE_HEX[tone])
            d["shade"], d["shade_desc"] = (r[9] or "").strip(), (r[10] or "").strip()
            scored.append((s, d))
        out += _draw(scored, 3, rng, per=1)
    for ttype, n, palette, part in (("lipstick", 2, None, "lip"), ("blush", 1, BLUSH, "cheek")):
        if ttype not in cat.types or part not in parts: continue
        base = (palette or LIP).get(under, (palette or LIP)["neutral"])
        if palette: cols = base
        else:
            pref = DEEP_LIP if tone == "deep" else LIGHT_LIP if tone in ("fair", "light") else None
            cols = ([c for c in pref if c in base] or pref) if pref else base
        picks = rng.sample(cols, min(n + 1, len(cols)))
        got = []
        for col in picks:
            res = cat.search("", params=(ttype, col, None, {"matte": "matte"}.get(finish)))
            if res and res[0]:
                d = rng.choice(res[0][:3]); d["why"] = [x for x in [f"{'An' if col[0] in 'aeiou' else 'A'} {col} that works with {(under + ' undertones') if under else 'your colouring'}"] + d.get("why", [])[:1]]
                if d["id"] not in [g["id"] for g in got + out]: got.append(d)
            if len(got) >= n: break
        out += got
    return out[:k]


# ---------------------------------------------------------------- fragrance
def fragrance(con, p, k=5, salt=None):
    want = [s for s in p.get("scent", []) if s in SCENTS]
    rows = con.execute("""SELECT product_id,name,brand,price_usd,rating,n_reviews,subcategory,tertiary,highlights FROM products
        WHERE category='Fragrance' AND subcategory IN ('Women','Men') AND n_reviews>=30 AND rating>=4""").fetchall()
    scored = []
    for r in rows:
        tags = _tags(r[8]); s, why = 0.0, []
        for sc in want:
            if SCENTS[sc][0] in tags: s += 3; why.append(f"A {SCENTS[sc][1]} scent")
        if want and s <= 0: continue
        if p.get("unisex") and "Unisex/ Genderless Scent" in tags: s += 1.5; why.append("Unisex")
        s += (r[4] - 4) + _pop(r[5])
        scored.append((s, _card(r, why)))
    return _draw(scored, k, _rng(salt, "fragrance", sorted(want)), per=3)


# ---------------------------------------------------------------- body
def body(con, p, k=5, salt=None):
    cons = [c for c in p.get("concerns", []) if c in BODY_TAGS]
    sensitive = bool(p.get("sensitive"))
    rows = con.execute("""SELECT product_id,name,brand,price_usd,rating,n_reviews,subcategory,tertiary,highlights FROM products
        WHERE category='Bath & Body' AND tertiary IN ('Body Lotions & Body Oils','Body Wash & Shower Gel','Scrub & Exfoliants','Hand Cream & Foot Cream')
        AND n_reviews>=20 AND rating>=4""").fetchall()
    scored = []
    for r in rows:
        tags = _tags(r[8]); s, why = 0.0, []
        for c in cons:
            if BODY_TAGS[c][0] in tags: s += 3; why.append(f"Good for {BODY_TAGS[c][1]}")
        if sensitive:
            if "Fragrance Free" in tags or "Hypoallergenic" in tags: s += 3; why.append("Fragrance-free / hypoallergenic")
            else: continue
        if cons and s <= 0: continue
        if "Hydrating" in tags: s += 0.5
        s += (r[4] - 4) + _pop(r[5])
        scored.append((s, _card(r, why)))
    return _draw(scored, k, _rng(salt, "body", sorted(cons), sensitive))


# ---------------------------------------------------------------- one entry point
def sections(con, cat, prof, salt=None, k=5):
    """prof = {"cats":[...], "skin":{...}, "hair":{...}, "makeup":{...}, "fragrance":{...}, "body":{...}}"""
    out, extra = [], {}
    for c in prof.get("cats") or ["skin"]:
        if c == "skin":
            r = skinmod.recommend(con, prof.get("skin") or {}, k=k, salt=salt); prods = r["products"]
            extra = {"profile": r["profile"], "focus": r["focus"], "top_ingredients": r.get("top_ingredients")}
        elif c == "hair": prods = hair(con, prof.get("hair") or {}, k, salt)
        elif c == "makeup": prods = makeup(con, cat, prof.get("makeup") or {}, k + 1, salt)
        elif c == "fragrance": prods = fragrance(con, prof.get("fragrance") or {}, k, salt)
        elif c == "body": prods = body(con, prof.get("body") or {}, k, salt)
        else: continue
        out.append({"key": c, "title": TITLES[c], "products": prods})
    return out, extra
