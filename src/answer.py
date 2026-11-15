"""Router + grounded answers. Every fact is tagged with its source; opinions are labelled as reviews."""
import difflib, os, random, re
from .guardrails import *
from .retrieval import BM25
from . import skin as skinmod, glossary
from .catalogue import Catalogue
from . import match

def pick(*opts): return random.choice(opts)


class Concierge:
    salt = 0
    def __init__(self, con):
        self.con = con
        self.cat = Catalogue(con)
        rows = con.execute("SELECT product_id,title,text,skin_type,rating FROM reviews").fetchall()
        self.idx = BM25([dict(pid=r[0], text=f"{r[1] or ''} {r[2] or ''}", skin=(r[3] or "").lower(), rating=r[4]) for r in rows])
        self.names = {r[0]: r[1] for r in con.execute("SELECT product_id,name FROM products")}

    def find_products(self, q, fuzzy=True):
        ql, hits = q.lower(), []
        for pid, n in sorted(self.names.items(), key=lambda x: -len(x[1] or "")):
            nl = (n or "").lower()
            if (len(nl) >= 12 or len(nl.split()) >= 2) and nl not in self.cat.types and nl in ql:
                hits.append((pid, n)); ql = ql.replace(nl, " ")  # longest match first; consume span
        if hits or not fuzzy: return hits
        words = set(re.findall(r"[a-z]{4,}", q.lower()))
        scored = []
        for pid, n in self.names.items():
            nw = {w for w in re.findall(r"[a-z]{4,}", n.lower())}
            hit = len(words & nw)
            if hit >= 3 and hit / max(len(nw), 1) >= 0.5: scored.append((hit, pid, n))   # most of the product's name must be in the question
        return [(p, n) for s, p, n in sorted(scored, reverse=True)][:2]

    def ingredient_search(self, term, k=6):
        g = glossary.find_ingredient(term)
        terms = {term.lower().strip()} | ({a for a in glossary.INGREDIENTS[g][0]} | {g} if g else set())
        terms |= {t[:-1] for t in terms if t.endswith("s") and len(t) > 4}      # "ceramides" -> "ceramide"
        like = " OR ".join("i.ingredient LIKE ?" for _ in terms)
        rows = self.con.execute(f"""SELECT p.product_id,p.name,p.brand,p.price_usd,p.rating,p.n_reviews,p.subcategory FROM products p JOIN ingredients i
            ON i.product_id=p.product_id WHERE ({like}) AND p.n_reviews>=1 GROUP BY p.product_id
            ORDER BY (p.n_reviews>=20) DESC, p.rating DESC, p.n_reviews DESC""", tuple(f"%{t}%" for t in terms)).fetchall()
        return len(rows), [dict(id=r[0], name=r[1], brand=r[2], price=r[3], rating=round(r[4] or 0, 1), reviews=r[5], type=r[6],
                                why=[f"Contains {term}"]) for r in rows[:k]]

    def card(self, pid, why=None):
        n, b, r, nr, pr = self.facts(pid)
        sub, shade, desc = self.con.execute("SELECT subcategory,shade,shade_desc FROM products WHERE product_id=?", (pid,)).fetchone()
        from .catalogue import swatch
        return dict(id=pid, name=n, brand=b, price=pr, rating=round(r or 0, 1), reviews=nr, type=sub,
                    shade=(shade or "").strip(), shade_desc=(desc or "").strip(), swatch=swatch(desc, shade), why=why or [])

    def ingredients_of(self, pid):
        return [r[0] for r in self.con.execute("SELECT ingredient FROM ingredients WHERE product_id=?", (pid,))]

    NEEDS_INGREDIENTS = {"Skincare", "Hair", "Bath & Body", "Men", "Mini Size"}

    def ingredient_line(self, pid, q, full=False):
        """Ingredient list only where it matters (skincare etc.), or when the user asks for it explicitly."""
        cat, shade, desc = self.con.execute("SELECT category,shade,shade_desc FROM products WHERE product_id=?", (pid,)).fetchone()
        asked = bool(re.search(r"ingredient|contain|made (of|with)|formula|what.?s in", q.lower()))
        if cat not in self.NEEDS_INGREDIENTS and not asked: return None
        ings = self.ingredients_of(pid)
        if not ings: return None
        if not (full or asked) and len(ings) > 12:
            return f"The key ingredients are {', '.join(ings[:12])}, plus {len(ings) - 12} more. Ask me for the full list if you'd like it."
        return f"Ingredients: {', '.join(ings)}"

    def facts(self, pid):
        return self.con.execute("SELECT name,brand,rating,n_reviews,price_usd FROM products WHERE product_id=?", (pid,)).fetchone()

    def reviews_for(self, pid, skin=None, k=3):
        f = lambda m: m["pid"] == pid and (not skin or m["skin"] == skin)
        return self.idx.search("good great love help bad irritat heavy", k=k, filt=f) or [
            m for m in self.idx.meta if m["pid"] == pid][:k]

    FREE = re.compile(r"gifted|complimentary|free (product|sample)|received (this|it|the product|a sample)|in exchange for|sephora (voxbox|insider)|influenster", re.I)

    def detail(self, pid, q, skin=None):
        ql = q.lower()
        c = self.card(pid)
        stars = {int(r[0]): r[1] for r in self.con.execute("SELECT CAST(rating AS INT),COUNT(*) FROM reviews WHERE product_id=? GROUP BY 1", (pid,)) if r[0]}
        rec = self.con.execute("SELECT AVG(recommended),COUNT(recommended) FROM reviews WHERE product_id=?", (pid,)).fetchone()
        ings = self.ingredients_of(pid)
        cat = self.con.execute("SELECT category FROM products WHERE product_id=?", (pid,)).fetchone()[0]
        asked_ing = bool(re.search(r"ingredient|contain|made (of|with)|formula|what.?s in", ql))
        asked_rev = bool(re.search(r"review|customer|say|suit|oily|dry|combination|opinion", ql))
        show_ing = bool(ings) and (cat in self.NEEDS_INGREDIENTS or asked_ing)
        focus = "ingredients" if asked_ing and not asked_rev else "reviews" if asked_rev and not asked_ing else "all"
        revs = []
        if focus != "ingredients":
            for x in self.reviews_for(pid, skin, k=4):
                t = (x["text"] or "").strip()
                revs.append(dict(text=t, rating=x["rating"], skin=x["skin"] or "", free=bool(self.FREE.search(t))))
        key = [i for i in ings if len(i) < 40 and i.lower() not in ("water", "water/aqua/eau", "aqua", "aqua/water/eau")][:8]
        keyroles = {i: glossary.short(i) for i in key if glossary.short(i) and i.lower() not in ("water/aqua/eau", "water")}
        return dict(card=c, stars=stars, recommend=(round(rec[0] * 100) if rec[0] is not None and rec[1] >= 5 else None, rec[1]),
                    ingredients=ings if show_ing else [], key=key if show_ing else [], roles=keyroles if show_ing else {},
                    reviews=revs, skin=skin, focus=focus, name=c["name"])

    def ask(self, q):
        if is_medical(q): return MEDICAL_NOTE
        ql = q.lower()
        self.ctx = {}
        if re.search(r"\b(what (is|are|does|do)|used for|good for|benefit|explain|tell me about|how does)\b", ql) and not re.search(r"customer|review|saying|say about", ql) and not self.find_products(q, fuzzy=False):
            ing = glossary.find_ingredient(ql)
            if ing: self.ctx = {"ingredient": ing}; return glossary.explain_ingredient(ing)
            typ = glossary.find_product_type(ql)
            if typ: self.ctx = {"ptype": typ}; return glossary.explain_type(typ)
        t = next((x for x in skinmod.SKIN_TYPES if x in ql), None)
        if re.search(r"\b(recommend|suggest|best|routine|suits?)\b", ql) and (t or "sensitive" in ql) and not self.find_products(q, fuzzy=False):
            r = skinmod.recommend(self.con, {"skin_type": t, "sensitive": "sensitive" in ql, "concerns": ["redness_sensitivity"] if "sensitive" in ql else []}, k=5, salt=self.salt)
            if not r["products"]: return "I couldn't find well-reviewed matches for that. Could you tell me a bit more about what you're after?"
            self.ctx["cards"] = r["products"]
            who = t or "sensitive"
            return pick(f"Here are my top picks for {who} skin. They match on ingredients, and reviewers with similar skin rate them highly.",
                        f"For {who} skin, these are the ones I'd look at first: good ingredients and strong reviews.",
                        f"I picked these with {who} skin in mind. They're well reviewed and have ingredients that tend to help.",
                        f"These should suit {who} skin nicely. Take a look and tell me if you'd like something lighter, richer or cheaper.")
        m = re.search(r"contain(?:s)?\s+([a-z\- ]+?)\??$", q.strip().lower()) or re.search(r"\b(niacinamide|ceramide|retinol|hyaluronic acid|squalane|glycerin)\b", q.lower())
        prods = self.find_products(q, fuzzy=not re.search(r"\bcontain", ql))
        if len(prods) > 1 and not self.find_products(q, fuzzy=False) and not re.search(r"\b(vs|versus|compare|difference)\b", ql): prods = prods[:1]   # loose match: pick the best one
        if m and not prods:
            term = m.group(1).strip(); total, cards_ = self.ingredient_search(term)
            if not total: return pick(f"I couldn't find any products with {term}. Want me to look for something similar?", f"Hmm, nothing in the catalogue lists {term}. Shall I try a related ingredient?")
            self.ctx["cards"] = cards_
            n_ = f"{total} product{'s' if total != 1 else ''}"
            return pick(f"I found {n_} with {term}. Here are the best-rated:", f"{term.title()} shows up in {n_}. These are the ones people rate highest:",
                        f"Here are the top-rated picks with {term}, out of {n_}:")
        if is_policy(q) and not prods: return POLICY_NOTE
        if len(prods) >= 2 or re.search(r"\b(vs|versus|difference|compare)\b", q.lower()) and prods:
            out = [pick("Here's how they compare:", "Side by side, here's how they stack up:", "Let's compare them:")]
            for pid, _ in prods:
                n, b, r, nr, pr = self.facts(pid)
                il = self.ingredient_line(pid, q)
                out.append(f"• {n} by {b}: ${pr:g}, rated {r:.1f}★ from {nr:,} reviews" + (f"\n   {il}" if il else ""))
            self.ctx["cards"] = [self.card(pid) for pid, _ in prods[:3]]
            return "\n".join(out)
        if prods:
            pid, _ = prods[0]
            skin = next((s for s in ("oily", "dry", "combination", "sensitive") if s in q.lower()), None)
            d = self.detail(pid, q, skin)
            self.ctx["detail"] = d
            n = d["name"]
            sk = f" with {skin} skin" if skin else ""
            return {"ingredients": pick(f"Here's what's in {n}.", f"This is the ingredient breakdown for {n}.", f"Let's look inside {n}."),
                    "reviews": pick(f"Here's what customers{sk} are saying about {n}.", f"Customers{sk} have a lot to say about {n}. Here are a few reviews.",
                                    f"A few honest reviews of {n}{(' from people with ' + skin + ' skin') if skin else ''}:")}.get(
                d["focus"], pick(f"Here's the full picture on {n}.", f"Here's everything on {n}.", f"Great choice to look into. Here's {n} at a glance."))
        self.ctx["notfound"] = True
        return pick("Hmm, I couldn't find that one. Could you give me a product name or an ingredient? You can also tell me your skin type, or ask for something like “a nude lipstick under $30”.",
                    "I'm not sure I caught that. Try a product name, an ingredient, or tell me what you're after, like “a gentle cleanser for dry skin”.",
                    "That one's not coming up for me. Want to tell me your skin type, or name a product or ingredient you're curious about?")

    # ---- personalised follow-up suggestions (only things the bot can actually answer)
    def suggest(self, q, profile=None, n=4, state=None):
        ql, out = q.lower(), []
        cats = (profile or {}).get("cats") or []
        hr, mk = (profile or {}).get("hair") or {}, (profile or {}).get("makeup") or {}
        if "hair" in cats: out += [f"Recommend a shampoo for {hr.get('type') or 'curly'} hair", "Best conditioner for dry hair"]
        if "makeup" in cats: out += [f"Show me a foundation for {mk.get('tone') or 'medium'} skin", "I want a red wine lipstick"]
        if "fragrance" in cats: out += ["Recommend a woody perfume", "Recommend a floral perfume"]
        if "body" in cats: out += ["Recommend a body lotion for dry skin"]
        CATCHIPS = {"hair": ["Recommend a shampoo for curly hair", "Best conditioner for dry hair", "Something for frizz and damage", "A hair mask for colour-treated hair"],
                    "fragrance": ["Recommend a woody perfume", "Recommend a floral perfume", "Recommend a fresh perfume", "A warm and spicy perfume"],
                    "body": ["Recommend a body lotion for dry skin", "A fragrance-free body lotion", "Body wash for sensitive skin", "A hand cream for dry hands"],
                    "makeup": ["Show me a foundation for tan skin", "I want a red wine lipstick", "Show me a blush", "A foundation for deep skin with cool undertone"]}
        lc = (state or {}).get("last_cat")
        if lc in CATCHIPS and not any(c in ql for c in ()):
            out += CATCHIPS[lc]
        last = (state or {}).get("search") if (state or {}).get("kind") == "search" else None
        if last:   # follow-ups that build on the remembered search
            ty, co, pr, fi = last
            if not pr: out.append("Make it under $20")
            else: out.append("Show cheaper options")
            if not fi: out.append("Show it in matte")
            out.append("Show it in " + ("pink" if co != "pink" else "nude"))
            if (state or {}).get("results"): out.append("Tell me about the first one")
        h = state or {}
        t = next((x for x in skinmod.SKIN_TYPES if x in ql), None) or (profile or {}).get("skin_type") or h.get("skin")
        prods = self.find_products(q, fuzzy=False)
        ing = glossary.find_ingredient(ql)
        ttype, colour, price, finish = self.cat.parse(q)
        tcat = self.con.execute("SELECT category FROM products WHERE tertiary=? LIMIT 1", (self.cat.types[ttype][0],)).fetchone() if ttype else None
        if ttype and not prods and tcat and tcat[0] == "Makeup":
            others = [c for c in ("red wine", "nude", "pink", "coral", "berry") if c != colour][:2]
            out += [f"I want a {others[0]} {ttype}", f"Show me a matte {ttype} under $30" if not price else f"Show me a {colour or 'nude'} {ttype}", f"I want a {others[1]} {ttype}"]
        elif prods:
            pid, name = prods[0]
            pc = self.con.execute("SELECT category FROM products WHERE product_id=?", (pid,)).fetchone()
            out.append(f"What are customers saying about {name}?")
            if pc and pc[0] in ("Skincare", "Bath & Body", "Men"): out.append(f"Does {name} suit {t or 'oily'} skin?")
            row = self.con.execute("SELECT subcategory,rating FROM products WHERE product_id=?", (pid,)).fetchone()
            other = self.con.execute("""SELECT name FROM products WHERE subcategory=? AND product_id!=? AND n_reviews>=100
                ORDER BY rating DESC LIMIT 1""", (row[0], pid)).fetchone() if row else None
            if other: out.append(f"Compare {name} and {other[0]}")
            for (i,) in self.con.execute("SELECT ingredient FROM ingredients WHERE product_id=? LIMIT 12", (pid,)):
                g = glossary.find_ingredient(i)
                if g and g not in ("fragrance",): out.append(f"What does {g} do?"); break
        elif ing:
            out += [f"Which products contain {ing}?", f"Recommend products for {t or 'dry'} skin"]
            out.append("What is a serum?" if ing in ("vitamin c", "retinol", "niacinamide", "hyaluronic acid") else "What is a moisturizer?")
        elif next((x for x in skinmod.SKIN_TYPES if x in ql), None) or "sensitive" in ql:
            focus = {"oily": "niacinamide", "dry": "ceramides", "combination": "hyaluronic acid", "normal": "vitamin c"}.get(t, "centella asiatica")
            out += [f"What does {focus} do?", f"Which products contain {focus.split()[0]}?"]
            out += [f"Best for {x} skin" for x in ("sensitive", "dry", "oily") if x != (t or "sensitive")][:2]
        elif glossary.find_product_type(ql):
            out += ["Recommend products for oily skin", "What does niacinamide do?", "Best for sensitive skin"]
        elif is_policy(q) or is_medical(q):
            out += ["Recommend products for sensitive skin", "What does ceramides do?"]
        if profile:
            tops = profile.get("top_ingredients") or [glossary.find_ingredient(skinmod.CONCERNS[k][0]) for k in (profile.get("focus") or [])[:1]]
            for g in [x for x in tops if x][:1]:   # an ingredient that is actually in the picks just shown
                out += [f"What does {g} do?", f"Which products contain {g}?"]
            if profile.get("skin_type"): out.append(f"Show me a {profile['skin_type']} skin routine")
        # what this customer has shown interest in earlier in the conversation
        RELATED = {"niacinamide": ["zinc", "salicylic acid"], "retinol": ["peptides", "hyaluronic acid"], "vitamin c": ["niacinamide"],
                   "hyaluronic acid": ["ceramides"], "ceramides": ["hyaluronic acid"], "salicylic acid": ["niacinamide"],
                   "glycolic acid": ["hyaluronic acid"], "centella asiatica": ["ceramides"]}
        for g in reversed(h.get("ings", [])[-3:]):
            out += [f"Which products contain {g}?"] + [f"What does {r} do?" for r in RELATED.get(g, [])[:1]]
        if h.get("product"):
            nm = h["product"]; out += [f"What are customers saying about {nm}?", f"Does {nm} suit {t or 'oily'} skin?"]
        if h.get("last_type") and h["last_type"] in self.cat.types:
            out.append(f"Show me a matte {h['last_type']} under $30")
        if t: out.append(f"Recommend products for {t} skin")
        out += ["Which products contain niacinamide?", "Recommend products for oily skin", "What is a serum?", "What does retinol do?",
                "What does hyaluronic acid do?", "What is a moisturizer?", "Best for sensitive skin", "Which products contain ceramides?"]
        asked = set(h.get("asked", [])) | {ql.strip("? .")}   # never suggest something already asked
        seen, res = set(), []
        for s in out:
            k = s.lower().rstrip("? .")
            if k not in asked and k not in seen: seen.add(k); res.append(s)
        return res[:n]


    def _run_search(self, params, st):
        res = self.cat.search("", params=params)
        prods, (ttype, colour, price, finish), total = res
        st["search"] = (ttype, colour, price, finish)           # remembered for follow-ups
        st["kind"] = "search"
        st["results"] = [p["name"] for p in prods]
        st["max_price"] = max([p["price"] for p in prods], default=None)
        label = " ".join(x for x in [finish, colour, ttype] if x) + (f" under ${price:g}" if price else "")
        if not prods: return {"text": pick(f"I couldn't find any {label} right now. Want to try a different shade, finish or budget?", f"No {label} turned up. Shall I look at nearby shades or a bigger budget?"), "products": []}
        if len(prods) == 1: return {"text": pick(f"This is the one I'd pick for {label}:", f"Just one match for {label}, and it's a good one:"), "products": prods}
        pl = " ".join(x for x in [finish, colour, ttype if ttype.endswith("s") else ttype + "s"] if x) + (f" under ${price:g}" if price else "")
        more = f" (out of {total} options)" if total > len(prods) else ""
        return {"text": pick(f"Here are my top {len(prods)} {pl}{more}:", f"I found some lovely {pl}{more}. These stand out:",
                             f"Take a look at these {pl}{more}:", f"These {pl} are the ones I'd start with{more}:"), "products": prods}

    ORD = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "last": -1}

    def ask_rich(self, q, state=None, _probe=False):
        """Returns {"text":..., "products":[...]}. `state` is a per-conversation dict (kept in memory only) so
        follow-ups like "make it under $20" or "what about its reviews" can use earlier messages."""
        st = state if state is not None else {}
        self.salt = st.setdefault("salt", random.random())
        st.pop("last_cat", None)       # set again if this turn is a hair / fragrance / body / makeup answer
        st["kind"] = "other"          # set to "search" again if this turn turns out to be a catalogue search
        ql = q.lower()
        t = next((x for x in skinmod.SKIN_TYPES if x in ql), None)
        if t: st["skin"] = t
        exact = self.find_products(q, fuzzy=False)
        ttype, colour, price, finish = self.cat.parse(q)
        last = st.get("search")
        # conversation history that drives the suggested questions (in RAM only, per session)
        st.setdefault("asked", []).append(ql.strip("? .")); del st["asked"][:-60]
        g = glossary.find_ingredient(ql)
        if g: st["ings"] = [x for x in st.get("ings", []) if x != g] + [g]
        if ttype: st["last_type"] = ttype
        if exact: st["product"] = exact[0][1]
        talk = self._smalltalk(ql)
        if talk: return {"text": talk, "products": []}
        offer = st.pop("offer", None)
        if offer and re.fullmatch(r"\s*(yes|yeah|yep|yup|sure|ok|okay|please|yes please|sure thing|show me|go ahead|do it)[ !.]*", ql):
            q = ql = offer
            exact = self.find_products(q, fuzzy=False); ttype, colour, price, finish = self.cat.parse(q)
        if st.get("awaiting") == "skin":
            t2 = next((x for x in skinmod.SKIN_TYPES if x in ql), None)
            if t2: st["skin"] = t2; st.pop("awaiting"); q = ql = f"recommend products for {t2} skin"; t = t2
        if is_medical(q):
            return {"text": self.ask(q), "products": []}
        if not _probe and not offer and len(ql.split()) <= 12:     # clear misspelling of a colour / finish / skin or hair word
            fx = self._typos(q, closed=True)
            if fx: return self._didyoumean(fx, st)
        # 1) refine the previous catalogue search ("make it under $20", "in matte", "cheaper", "show it in pink")
        mods = price or colour or finish or re.search(r"\b(cheaper|affordable|budget|another|different|instead|more options|show more)\b", ql)
        if not ttype and last and mods and not exact:
            p_ = price
            if not p_ and re.search(r"cheaper|affordable|budget", ql):
                base = last[2] or st.get("max_price")
                p_ = round(base * 0.7) if base else None
            return self._run_search((last[0], colour or last[1], p_ or last[2], finish or last[3]), st)
        cat_resp = None if any(len(n) >= 18 for _, n in exact) else self._category(q, ql, st)   # short product names ("Body Lotion") are generic, not a specific product
        if cat_resp: return cat_resp
        # 2) a new catalogue search
        if not exact and self.cat.is_search(q):
            if self.cat.search(q) is not None:
                return self._run_search((ttype, colour, price, finish), st)
        # 3) refer back to earlier results / product ("the second one", "its reviews", "compare it with ...")
        if not exact:
            name = None
            m = re.search(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|last)\b(?: one| pick| option| product)?", ql)
            if m and st.get("results"):
                try: name = st["results"][self.ORD[m.group(1)]]
                except IndexError: name = None
            if not name and st.get("product") and re.search(r"\b(it|its|this|that|this one|that one)\b", ql):
                name = st["product"]
            if name: q = f"{q} {name}"; exact = self.find_products(q, fuzzy=False)
        # 4) remembered skin type for recommendations
        if not t and st.get("skin") and re.search(r"\b(recommend|suggest|best|routine)\b", ql) and not exact:
            q = f"{q} for {st['skin']} skin"
        if exact: st["product"] = exact[0][1]
        if re.search(r"\b(recommend|suggest|routine)\b", ql) and not exact and not t and not st.get("skin") and not glossary.find_ingredient(ql) \
                and not re.search(r"sensitive", ql) and not ttype:
            st["awaiting"] = "skin"
            return {"text": "Happy to help! What's your skin type: oily, dry, combination or normal? And is there anything you'd like to focus on, like blemishes, dark spots or dryness?", "products": []}
        text = self.ask(q)
        if (self.ctx or {}).get("notfound") and not _probe:       # nothing matched: maybe a typo in a product or ingredient name
            fx = self._typos(q, closed=False)
            if fx and self._works(fx, st): return self._didyoumean(fx, st)
        ing = (self.ctx or {}).get("ingredient"); typ = (self.ctx or {}).get("ptype")
        if ing: st["offer"] = f"Which products contain {ing}?"
        out = {"text": text, "products": (self.ctx or {}).get("cards", [])}
        if (self.ctx or {}).get("detail"): out["detail"] = self.ctx["detail"]; out["products"] = []
        return out


    HAIR_CONC = {"frizz": r"frizz", "dryness": r"\bdry (hair|ends)|dryness|hydrat|moistur", "damage": r"damag|breakage|split ends|repair|bleach",
                 "color_care": r"colou?r|dyed|highlight", "volume": r"volum|flat|limp|fine hair", "thinning": r"thinning|hair (loss|fall)",
                 "dry_scalp": r"dandruff|flak|dry scalp|itchy scalp", "oily_scalp": r"oily scalp|greasy|oily hair", "shine": r"\bshin"}
    SCENT_W = {"floral": r"floral|flower|rose|jasmine", "fresh": r"fresh|citrus|clean|aquatic", "woody": r"wood|earthy|sandal|cedar", "warm": r"warm|spic|vanilla|amber|musk"}
    TONE_W = {"fair": r"\b(fair|pale|porcelain)\b", "light": r"\blight\b", "medium": r"\bmedium\b", "tan": r"\b(tan|tanned)\b", "deep": r"\b(deep|dark)\b"}
    UNDER_W = {"warm": r"\bwarm|golden|yellow", "cool": r"\bcool|pink|rosy", "neutral": r"\bneutral", "olive": r"\bolive"}

    def _category(self, q, ql, st):
        """Personalised picks beyond skincare, from free text: hair, fragrance, body care and tone-matched base makeup."""
        salt = self.salt
        verbs = re.search(r"\b(recommend|suggest|best|need|want|looking|find|show|something|for|good)\b", ql)
        if re.search(r"contain|ingredient|what (is|are|does)|customers|reviews?|saying", ql): return None
        if st.get("awaiting") == "hair" or re.search(r"\b(hair|shampoo|conditioner|scalp|curl|curls|curly|coily|wavy|frizz|dandruff|leave-in)\b", ql):
            htype = next((t for t in match.HAIR_TYPES if re.search(r"\b" + t, ql)), "curly" if re.search(r"\bcurls?\b", ql) else None)
            cons = [c for c, rx in self.HAIR_CONC.items() if re.search(rx, ql)]
            if not htype and not cons and st.get("awaiting") != "hair":
                if not verbs: return None
                st["awaiting"] = "hair"
                return {"text": pick("Happy to help with your hair! What's it like (straight, wavy, curly or coily), and what would you like to improve, like frizz, dryness, damage or an oily scalp?",
                                     "Let's find your match! Tell me your hair type (straight, wavy, curly, coily) and anything you'd like to fix, such as frizz, dryness, colour care or volume."), "products": []}
            st.pop("awaiting", None)
            avoid = [a for a, rx in (("sulfates", r"sulf"), ("silicones", r"silicon"), ("fragrance", r"fragrance|scent")) if re.search(rx + r".{0,6}(free|less)|(no|without|avoid) " + rx, ql)]
            prods = match.hair(self.con, {"type": htype, "concerns": cons, "avoid": avoid}, 5, salt)
            if not prods: return {"text": "I couldn't find a strong match for that. Want to try a different hair concern?", "products": []}
            what = " and ".join(x for x in [htype and f"{htype} hair", *[match.HAIR_TAGS[c][1] for c in cons[:2]]] if x)
            st["last_cat"] = "hair"
            return {"text": pick(f"Here are my top picks for {what or 'your hair'}:", f"For {what or 'your hair'}, these are the ones I'd try first:", f"I found some great options for {what or 'your hair'}:"), "products": prods}
        if re.search(r"\b(perfume|fragrance|cologne|scent|eau de (parfum|toilette))\b", ql) and not re.search(r"free|without|avoid|allerg|sensitiv|no fragrance", ql) and (verbs or len(ql.split()) <= 8):
            want = [k for k, rx in self.SCENT_W.items() if re.search(rx, ql)]
            prods = match.fragrance(self.con, {"scent": want, "unisex": bool(re.search(r"unisex|genderless", ql))}, 5, salt)
            if not prods: return None
            what = " and ".join(match.SCENTS[k][1] for k in want[:2]); st["last_cat"] = "fragrance"
            return {"text": pick(f"Here are some {what + ' ' if what else ''}fragrances I think you'll love:", f"If you like {what or 'a signature scent'}, start with these:", f"These {what + ' ' if what else ''}scents are well loved:"), "products": prods}
        if re.search(r"\bbody (lotion|wash|butter|care|oil|scrub|cream|moisturi[sz]er)|hand cream|foot cream|shower gel", ql):
            cons = [c for c, rx in (("dryness", r"dry|dryness|hydrat"), ("dullness", r"dull|rough|texture"), ("firmness", r"firm|sagging")) if re.search(rx, ql)]
            prods = match.body(self.con, {"concerns": cons, "sensitive": bool(re.search(r"sensitive|fragrance.free|unscented", ql))}, 5, salt)
            if not prods: return None
            st["last_cat"] = "body"
            return {"text": pick("Here are my top body care picks" + (" for " + " and ".join(match.BODY_TAGS[c][1] for c in cons) if cons else "") + ":", "These body care products are well reviewed:"), "products": prods}
        base = re.search(r"\b(foundation|concealer|tinted moisturi[sz]er|bb cream|cc cream)\b", ql)
        tone = next((t for t, rx in self.TONE_W.items() if re.search(rx, ql)), None)
        if base and tone and re.search(r"skin|shade|tone|complexion|for", ql):
            under = next((u for u, rx in self.UNDER_W.items() if re.search(rx, ql)), None)
            prods = match.makeup(self.con, self.cat, {"tone": tone, "undertone": under}, 5, salt, parts=("base",))
            if prods:
                st["last_cat"] = "makeup"
                return {"text": pick(f"These should match {tone} skin" + (f" with {under} undertones" if under else "") + ":", f"Shades that work for {tone} skin" + (f" ({under} undertone)" if under else "") + ":"), "products": prods}
        return None


    COMMON = set("""what does do did is are was were the and for with without about under over below above from into onto your you my me our any all some more less
        most best better worse good great nice please show tell give find need want looking look like love have has had can could would should will
        recommend recommended suggest suggestion suggestions products product ingredient ingredients customers customer reviews review saying says
        said price cheap cheaper cheapest expensive budget make made make it its this that these those there here which who whom whose when where why how
        skin hair body face lips eyes makeup make-up beauty care routine concern concerns type types kind kinds shade shades colour color colours colors
        something anything everything thing things other another different instead option options pick picks than then very really just also only
        first second third last next one ones two three four five six also still even ever never always often again once twice
        dry oil oily eye red tan spf new top big low high hot gel mix mat fix day night sun aha bha not yes yeah yep okay thanks""".split())

    TYPO_MAP = {"drie": "dry", "dri": "dry", "dryy": "dry", "oyly": "oily", "olly": "oily", "oli": "oily", "sensative": "sensitive", "sensetive": "sensitive"}

    def _vocab(self):
        if getattr(self, "_v", None): return self._v
        from .catalogue import COLOURS, FINISH
        closed = set(COLOURS) | set(FINISH) | set(skinmod.SKIN_TYPES) | set(match.HAIR_TYPES) | set(match.TONES) | set(match.UNDERTONES) \
            | {"sensitive", "combination", "floral", "fresh", "woody", "spicy", "matte", "glossy", "satin", "shimmer", "frizz", "dandruff"}
        closed |= {w for c in list(COLOURS) for w in c.split()}
        closed |= {"shampoo", "conditioner", "perfume", "fragrance", "cologne", "lipstick", "foundation", "concealer", "mascara", "eyeliner", "blush",
                   "moisturizer", "moisturiser", "cleanser", "serum", "sunscreen", "lotion", "retinol", "niacinamide", "ceramide", "hyaluronic", "peptide",
                   "vitamin", "salicylic", "glycolic", "bronzer", "primer", "toner", "recommend", "suggest"}
        openv = set(closed)
        for g, (al, *_r) in glossary.INGREDIENTS.items():
            openv |= {w for t in [g] + list(al) for w in re.findall(r"[a-z]{4,}", t.lower())}
        for t in self.cat.types: openv |= {w for w in re.findall(r"[a-z]{4,}", t)}
        for _n, (_d, kws) in glossary.PRODUCT_TYPES.items(): openv |= {w for k in kws for w in re.findall(r"[a-z]{4,}", k)}
        openv |= {"perfume", "fragrance", "cologne", "shampoo", "conditioner", "lotion", "moisturizer", "cleanser", "serum", "sunscreen", "foundation",
                  "concealer", "lipstick", "mascara", "eyeliner", "blush", "bronzer", "primer", "toner", "retinol", "niacinamide", "ceramide", "peptide"}
        for r in self.con.execute("SELECT DISTINCT brand FROM products"):
            openv |= {w for w in re.findall(r"[a-z]{5,}", (r[0] or "").lower())}
        for n in self.names.values():
            openv |= {w for w in re.findall(r"[a-z]{5,}", (n or "").lower())}
        english = set()
        if os.path.exists("/usr/share/dict/words"):
            try: english = {w.strip().lower() for w in open("/usr/share/dict/words", errors="ignore")}
            except OSError: english = set()
        self._v = (closed, openv, sorted(closed), sorted(openv | self.COMMON), english)
        return self._v

    def _typos(self, q, closed):
        """Return q with likely misspelt domain words fixed (None if nothing to fix)."""
        c, o, cl, ol, eng = self._vocab()
        vocab, vlist, cut = (c, cl, 0.84) if closed else (o, ol, 0.75)
        changed = [0]
        def fix(m):
            w = m.group().lower()
            base = w[:-1] if w.endswith("s") else w
            if w in o or base in o or w in self.COMMON or base in self.COMMON or w in eng or base in eng or changed[0] >= 2: return m.group()
            hit = [self.TYPO_MAP[w]] if w in self.TYPO_MAP else difflib.get_close_matches(w, vlist, n=1, cutoff=cut)
            if not hit: return m.group()
            changed[0] += 1
            return hit[0].capitalize() if m.group()[0].isupper() else hit[0]
        out = re.sub(r"[A-Za-z][A-Za-z'\-]{2,}", fix, q)
        return out if changed[0] and out.lower() != q.lower() else None

    def _didyoumean(self, fix, st):
        st["offer"] = fix
        return {"text": pick(f"Did you mean “{fix}”?", f"Hmm, did you mean “{fix}”? Tap it below, or just say yes.", f"I think you meant “{fix}”. Shall I go with that?"),
                "products": [], "didyoumean": fix}

    def _works(self, q, st):
        tmp = {k: (list(v) if isinstance(v, list) else v) for k, v in st.items()}
        r = self.ask_rich(q, tmp, _probe=True)
        return bool(r.get("products") or r.get("detail") or (r.get("text") and not (self.ctx or {}).get("notfound")))

    def _smalltalk(self, ql):
        s = ql.strip(" !.?")
        if re.fullmatch(r"(hi+|hello+|hey+|hiya|namaste|good (morning|afternoon|evening)|hi there|hello there)", s):
            return pick("Hi there! 👋 I'm your Sephora Beauty Concierge. Tell me what you're looking for, or ask about an ingredient, and I'll help you find it.",
                        "Hello! Lovely to see you. Are you after a product, a shade, or some advice for your skin?", "Hey! 💄 What can I help you find today: makeup, skincare, or something specific?")
        if re.fullmatch(r"(thanks|thank you|thx|ty|thanks a lot|thank you so much|cheers)", s):
            return pick("You're so welcome! Anything else I can help you find?", "Happy to help! Want to look at anything else?", "Anytime! Shout if you'd like another recommendation.")
        if re.fullmatch(r"(bye|goodbye|see you|see ya|good night)", s):
            return pick("Bye for now! Come back any time you need a beauty recommendation. 💄", "Take care! I'm here whenever you need me. ✨")
        if re.fullmatch(r"(how are you|how are you doing|how's it going)", s):
            return pick("Doing great, thanks for asking! What can I help you find today?", "All good here! What are we shopping for?")
        if re.search(r"\b(who are you|what can you do|what do you do|help me|how does this work)\b", s):
            return ("I'm your beauty concierge. I can find products by type, shade or budget, explain what ingredients do, "
                    "compare products and share what customers say. For personal picks, tell me your skin type or try the skin check on the right.")
        return None
