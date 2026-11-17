import json, os, sys, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from src.db import build
from src.answer import Concierge
from src import skin, match
root = os.path.dirname(os.path.abspath(__file__))
k = os.path.join(root, "data/kaggle")
d = k if os.path.exists(os.path.join(k, "product_info.csv")) else os.path.join(root, "data/sample")
print(f"Loading data from {d} (may take ~20s)...", flush=True)
bot = Concierge(build(os.environ.get("DB_PATH", os.path.join(root, "sephora.db")), d))
PORT = int(os.environ.get("PORT", 8000))
MAX_BODY = 8 * 1024 * 1024

SESSIONS = {}   # conversation memory: in RAM only, never written to disk, lost on restart (capped)

ALLOWED = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]   # e.g. https://my-app.vercel.app

class H(BaseHTTPRequestHandler):
    def _cors(self):
        o = (self.headers.get("Origin") or "").rstrip("/")
        if o and o in ALLOWED:
            self.send_header("Access-Control-Allow-Origin", o); self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Session, ngrok-skip-browser-warning")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            if self.headers.get("Access-Control-Request-Private-Network"): self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.send_header("Content-Length", "0"); self.end_headers()

    def _state(self):
        sid = (self.headers.get("X-Session") or "anon")[:64]
        if sid not in SESSIONS:
            if len(SESSIONS) >= 300: SESSIONS.pop(next(iter(SESSIONS)))
            SESSIONS[sid] = {}
        return SESSIONS[sid]

    def _match(self, c, a=None):
        """Combine the person's answers (and, if given, the photo findings) into one profile and recommend across categories."""
        c = c if isinstance(c, dict) and "cats" in c else {"cats": ["skin"], "skin": c if isinstance(c, dict) else {}}
        st = self._state(); salt = st.setdefault("salt", __import__("random").random())
        cats = [x for x in c.get("cats", []) if x in match.TITLES] or ["skin"]
        sk, hr, mk = dict(c.get("skin") or {}), dict(c.get("hair") or {}), dict(c.get("makeup") or {})
        mine = [x for x in sk.get("concerns", []) if x in skin.CONCERNS]
        if a:
            sk["skin_type"] = a.get("skin_type") if a.get("skin_type") in skin.SKIN_TYPES else (sk.get("skin_type") or None)
            sk["concerns"] = list(dict.fromkeys(a.get("concerns", []) + mine))
            sk["weights"] = {**a.get("weights", {}), **{x: 3 for x in mine}}
            mk["tone"] = mk.get("tone") or a.get("skin_tone"); mk["undertone"] = mk.get("undertone") or a.get("undertone")
            h = a.get("hair") or {}
            if h.get("visible"):
                hr["type"] = hr.get("type") or h.get("texture")
                lv = {"mild": 1, "moderate": 2, "notable": 3}
                hc = [k for k in ("frizz", "dryness", "damage") if lv.get(h.get(k), 0) >= 2]
                if h.get("scalp_flakes") in ("moderate", "notable"): hc.append("dry_scalp")
                if h.get("shine") == "dull": hc.append("shine")
                if h.get("thickness") == "fine": hc.append("volume")
                if h.get("colour_treated"): hc.append("color_care")
                hr["concerns"] = list(dict.fromkeys(hc + [x for x in hr.get("concerns", []) if x in match.HAIR_TAGS]))
                hr["weights"] = {**{k: lv.get(h.get(k), 2) for k in hc}, **{x: 3 for x in c.get("hair", {}).get("concerns", [])}}
        b = dict(c.get("body") or {})
        if not b.get("concerns") and sk.get("skin_type") in ("dry", "normal"): b["concerns"] = ["dryness"]
        b["sensitive"] = b.get("sensitive") or "fragrance" in sk.get("avoid", []) or "redness_sensitivity" in sk.get("concerns", [])
        prof = {"cats": cats, "skin": sk, "hair": hr, "makeup": mk, "fragrance": c.get("fragrance") or {}, "body": b}
        secs, extra = match.sections(bot.con, bot.cat, prof, salt)
        out = {"sections": secs, "cats": cats, **extra}
        if "skin" in cats:
            st["skin"] = extra["profile"].get("skin_type") or st.get("skin")
            st["focus"] = extra["focus"]
            out["products"] = secs[cats.index("skin")]["products"]
            out["suggestions"] = bot.suggest("", extra["profile"] | {"focus": extra["focus"], "top_ingredients": extra.get("top_ingredients")})
        else:
            out["profile"] = {"skin_type": None, "concerns": [], "avoid": []}; out["focus"] = []; out["products"] = []
            out["suggestions"] = bot.suggest("", {"cats": cats, **{"hair": hr, "makeup": mk}})
        return out

    def _send(self, obj, ctype="application/json", code=200):
        b = (obj if isinstance(obj, str) else json.dumps(obj)).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store"); self._cors(); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/config":
            pv = skin.provider(); return self._send({"image_analysis": bool(pv), "provider": pv, "local": pv == skin.LOCAL_NAME})
        if self.path.split("?")[0] == "/config.js":
            return self._send(open(os.path.join(root, "web/config.js"), encoding="utf-8").read(), "application/javascript")
        page = "web/chat.html" if self.path.split("?")[0] in ("/chat", "/chat.html") else "web/index.html"   # "/" is the welcome page
        self._send(open(os.path.join(root, page), encoding="utf-8").read(), "text/html")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_BODY: return self._send({"error": "Image too large"}, code=413)
        body = self.rfile.read(n)
        try:
            if self.path == "/ask":
                q = body.decode(); st = self._state(); r = bot.ask_rich(q, st); r["suggestions"] = bot.suggest(q, state=st)
                if r.get("didyoumean"): r["suggestions"] = [r["didyoumean"]] + [x for x in r["suggestions"] if x != r["didyoumean"]][:3]
                return self._send(r)
            data = json.loads(body)
            if self.path in ("/recommend", "/match"):
                return self._send(self._match(data))
            if self.path == "/analyze":
                if not data.get("consent"): return self._send({"error": "Consent is required."}, code=400)
                img = data.pop("image", ""); consult = data.get("consult") or {}
                try:
                    a = skin.analyze_image(img, data.get("media_type", "image/jpeg"))
                finally:
                    del img, data, body   # image bytes live only in this request's memory; nothing is stored
                if not a.get("usable", True) and not (a.get("hair") or {}).get("visible"):
                    return self._send({"error": "I couldn't see your skin or hair clearly in that photo. Could you try again in bright, even light?"}, code=422)
                if os.environ.get("DEBUG_ANALYSIS"):   # opt-in: print the derived findings (never the photo) so results can be compared across photos
                    print("[analysis]", json.dumps({k: a.get(k) for k in ("skin_type", "zones", "skin_tone", "undertone", "findings", "freckles", "temporary", "hair", "concerns", "confidence")}), file=sys.stderr, flush=True)
                return self._send({"analysis": a, "deleted": True, **self._match(consult, a)})
        except RuntimeError as e:
            if str(e) == "NO_KEY": return self._send({"error": "Photo skin checks aren't available right now. You can still get personalised picks from the skin questions."}, code=503)
            return self._send({"error": "Sorry, something went wrong. Please try again."}, code=500)
        except urllib.error.HTTPError as e:
            try: msg = json.load(e)["error"]["message"]
            except Exception: msg = ""
            print(f"[analyze] {skin.provider()} API error {e.code}: {msg[:200]}", file=sys.stderr, flush=True)
            hint = {401: "The API key was rejected.", 429: "Quota or rate limit reached — check billing/credits.",
                    404: "That model isn't available to this key."}.get(e.code, "The provider returned an error.")
            return self._send({"error": "Sorry, the skin check isn't available right now. You can still get picks from the skin questions instead."}, code=502)
        except Exception as e:
            print(f"[analyze] {type(e).__name__}: {str(e)[:200]}", file=sys.stderr, flush=True)
            return self._send({"error": "Sorry, I couldn't check that photo just now. Please try again, or use the skin questions instead."}, code=500)
        self._send({"error": "Not found"}, code=404)

    def log_message(self, *a): pass   # never log request details
print(f"Open http://localhost:{PORT}", flush=True); HTTPServer(("127.0.0.1", PORT), H).serve_forever()
