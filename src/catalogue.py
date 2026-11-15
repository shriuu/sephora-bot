"""Catalogue search: product type + colour + price -> product cards."""
import re

# colour phrase -> words to look for in shade name / shade description / product name
COLOURS = {
    "red wine": ["wine", "burgundy", "merlot", "bordeaux", "cabernet", "oxblood", "maroon", "deep red", "dark red", "berry red", "garnet", "claret", "vamp", "mahogany", "mulled wine", "black cherry", "dark berry", "deep berry"],
    "wine": ["wine", "burgundy", "merlot", "bordeaux", "cabernet", "oxblood", "maroon", "deep red", "dark red", "garnet", "claret"],
    "burgundy": ["burgundy", "wine", "merlot", "bordeaux", "maroon", "oxblood", "deep red"],
    "berry": ["berry", "raspberry", "cranberry", "plum", "mulberry", "blackberry"],
    "plum": ["plum", "aubergine", "mulberry", "grape", "deep purple"],
    "red": ["red", "cherry", "ruby", "scarlet", "crimson", "tomato", "brick"],
    "pink": ["pink", "rose", "fuchsia", "magenta", "bubblegum", "blush"],
    "nude": ["nude", "beige", "tan", "caramel", "bare", "neutral", "peachy"],
    "coral": ["coral", "peach", "salmon", "papaya"],
    "orange": ["orange", "tangerine", "terracotta", "rust", "burnt"],
    "mauve": ["mauve", "dusty rose", "dusty pink", "rosewood", "taupe"],
    "brown": ["brown", "chocolate", "mocha", "espresso", "cocoa", "chestnut"],
    "purple": ["purple", "violet", "lavender", "lilac", "orchid", "grape"],
    "blue": ["blue", "navy", "teal", "cobalt"],
    "green": ["green", "olive", "emerald", "khaki"],
    "black": ["black", "noir", "onyx"],
    "white": ["white", "pearl", "ivory"],
    "yellow": ["yellow", "gold", "golden", "mustard"],
    "silver": ["silver", "metallic", "grey", "gray"],
}
FINISH = {"matte": "Matte Finish", "satin": "Satin Finish", "glossy": "Glossy Finish", "shimmer": "Shimmer Finish", "creamy": "Cream Formula"}
SHOP = re.compile(r"\b(want|need|looking for|look for|show me|find me|find|give me|any|suggest|recommend|buy|get me|which|best|do you have|have you got)\b|\bunder\b|\bbelow\b", re.I)


# word in a shade name/description -> display colour (most specific first)
SWATCH = [("mulled wine", "#6b1d34"), ("wine", "#6b1d34"), ("burgundy", "#7a1f3d"), ("merlot", "#6e1b36"), ("bordeaux", "#6a1830"),
          ("oxblood", "#5a1620"), ("maroon", "#6b1626"), ("mahogany", "#5c2018"), ("black cherry", "#4a1224"), ("cherry", "#b3122f"),
          ("deep berry", "#7b1f48"), ("berry", "#8e2750"), ("raspberry", "#b0204f"), ("plum", "#5e2a52"), ("fuchsia", "#d6246e"),
          ("magenta", "#c2185b"), ("scarlet", "#c8102e"), ("crimson", "#b0122c"), ("brick", "#a63d2f"), ("red", "#c0152f"),
          ("coral", "#ef6f5e"), ("peach", "#f2a488"), ("salmon", "#f08a7a"), ("orange", "#e8742c"), ("terracotta", "#c0623f"),
          ("rust", "#b5532a"), ("dusty rose", "#c98a95"), ("mauve", "#a9718a"), ("rose", "#d9708a"), ("pink", "#e8789a"),
          ("nude", "#d2a187"), ("beige", "#d9b99b"), ("caramel", "#b97b50"), ("taupe", "#9c7c6d"), ("tan", "#c19a6b"),
          ("chocolate", "#5a3325"), ("brown", "#7a4a35"), ("mocha", "#6b4535"), ("purple", "#7b4a9c"), ("violet", "#6f45a8"),
          ("lilac", "#b79bd6"), ("blue", "#3f6fb5"), ("navy", "#223a6b"), ("teal", "#2a8a8a"), ("green", "#3f8a5a"),
          ("black", "#1c1c1c"), ("white", "#f3f1ee"), ("pearl", "#ede6df"), ("gold", "#c9a44c"), ("silver", "#b9bcc2"), ("neutral", "#cfa88f")]


def swatch(*texts):
    t = " ".join(x or "" for x in texts).lower()
    for w, hexv in SWATCH:
        if re.search(r"\b" + re.escape(w), t): return hexv
    return None


class Catalogue:
    def __init__(self, con):
        self.con = con
        self.types = {}  # tertiary lower -> [tertiary names that satisfy it]
        names = [r[0] for r in con.execute("SELECT DISTINCT tertiary FROM products WHERE tertiary IS NOT NULL AND tertiary!=''")]
        for n in names:
            low = n.lower()
            if low.endswith("lipstick"): self.types.setdefault("lipstick", []).append(n)
            self.types.setdefault(low, []).append(n)
            if low.endswith("s") and not low.endswith("ss"): self.types.setdefault(low[:-1], []).append(n)
        for alias, base in {"lip color": "lipstick", "lippie": "lipstick", "lip tint": "lip stain", "lipgloss": "lip gloss",
                            "eyeshadows": "eyeshadow", "eye shadow": "eyeshadow", "kajal": "eyeliner", "kohl": "eyeliner"}.items():
            if base in self.types: self.types[alias] = self.types[base]

    def parse(self, q):
        ql = q.lower()
        ttype = next((t for t in sorted(self.types, key=len, reverse=True) if re.search(r"\b" + re.escape(t) + r"s?\b", ql)), None)
        colour = next((c for c in COLOURS if re.search(r"\b" + c + r"\b", ql)), None)
        price = re.search(r"(?:under|below|less than|max|upto|up to)\s*\$?\s*(\d+)", ql)
        finish = next((f for f in FINISH if f in ql), None)
        return ttype, colour, (float(price.group(1)) if price else None), finish

    def is_search(self, q):
        ttype, colour, price, finish = self.parse(q)
        return bool(ttype and (colour or price or finish or SHOP.search(q) or len(q.split()) <= 4))

    def search(self, q, k=6, params=None):
        ttype, colour, price, finish = params or self.parse(q)
        if not ttype: return None
        tert = self.types[ttype]
        sql = f"SELECT product_id,name,brand,price_usd,rating,n_reviews,tertiary,shade,shade_desc,highlights FROM products WHERE tertiary IN ({','.join('?'*len(tert))}) AND n_reviews>=1"
        args = list(tert)
        if price: sql += " AND price_usd<=?"; args.append(price)
        rows = self.con.execute(sql, args).fetchall()
        words = COLOURS.get(colour, [])
        out = []
        for pid, name, brand, pr, rating, nrev, tt, shade, desc, hl in rows:
            hay_shade = f"{shade or ''} {desc or ''}".lower()
            hay_name = (name or "").lower()
            cscore = 0
            if colour:
                cscore = sum(2 for w in words if re.search(r"\b" + re.escape(w), hay_shade)) + sum(1 for w in words if w in hay_name)
                if cscore == 0: continue
            if finish and FINISH[finish].lower() not in (hl or "").lower() and finish not in (name or "").lower() and finish not in hay_shade: continue
            score = cscore * 3 + (rating or 0) + min(nrev or 0, 500) / 500
            out.append((score, dict(id=pid, name=name, brand=brand, price=pr, rating=round(rating or 0, 1), reviews=nrev, type=tt,
                                    shade=(shade or "").strip(), shade_desc=(desc or "").strip(), swatch=swatch(desc, shade),
                                    why=[x for x in [f"Shade: {shade}" + (f" ({desc})" if desc else "") if shade else "", self._finish(hl)] if x])))
        out.sort(key=lambda x: -x[0])
        return [d for _, d in out[:k]], (ttype, colour, price, finish), len(out)

    @staticmethod
    def _finish(hl):
        bits = [f for f in ("Matte Finish", "Satin Finish", "Glossy Finish", "Cream Formula", "Long-wearing", "Hydrating", "Vegan", "Cruelty-Free") if f.lower() in (hl or "").lower()]
        return ", ".join(bits[:4])
