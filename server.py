import json, os, sys, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from src.db import build
from src.answer import Concierge
from src import skin
root = os.path.dirname(os.path.abspath(__file__))
k = os.path.join(root, "data/kaggle")
d = k if os.path.exists(os.path.join(k, "product_info.csv")) else os.path.join(root, "data/sample")
print(f"Loading data from {d} (may take ~20s)...", flush=True)
bot = Concierge(build(os.environ.get("DB_PATH", os.path.join(root, "sephora.db")), d))
PORT = int(os.environ.get("PORT", 8000))
MAX_BODY = 8 * 1024 * 1024

SESSIONS = {}   # conversation memory: in RAM only, never written to disk, lost on restart (capped)

class H(BaseHTTPRequestHandler):
    def _state(self):
        sid = (self.headers.get("X-Session") or "anon")[:64]
        if sid not in SESSIONS:
            if len(SESSIONS) >= 300: SESSIONS.pop(next(iter(SESSIONS)))
            SESSIONS[sid] = {}
        return SESSIONS[sid]

    def _send(self, obj, ctype="application/json", code=200):
        b = (obj if isinstance(obj, str) else json.dumps(obj)).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/config":
            pv = skin.provider(); return self._send({"image_analysis": bool(pv), "provider": pv, "local": pv == skin.LOCAL_NAME})
        self._send(open(os.path.join(root, "web/index.html"), encoding="utf-8").read(), "text/html")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_BODY: return self._send({"error": "Image too large"}, code=413)
        body = self.rfile.read(n)
        try:
            if self.path == "/ask":
                q = body.decode(); st = self._state(); r = bot.ask_rich(q, st); r["suggestions"] = bot.suggest(q, state=st); return self._send(r)
            data = json.loads(body)
            if self.path == "/recommend":
                r = skin.recommend(bot.con, data); r["suggestions"] = bot.suggest("", r["profile"] | {"focus": r["focus"], "top_ingredients": r.get("top_ingredients")})
                if r["profile"].get("skin_type"): self._state()["skin"] = r["profile"]["skin_type"]
                return self._send(r)
            if self.path == "/analyze":
                if not data.get("consent"): return self._send({"error": "Consent is required."}, code=400)
                img = data.pop("image", ""); feel = data.get("consult") or {}
                try:
                    a = skin.analyze_image(img, data.get("media_type", "image/jpeg"))
                finally:
                    del img, data, body   # image bytes live only in this request's memory; nothing is stored
                if not a.get("usable", True):
                    return self._send({"error": "I couldn't see your skin clearly in that photo. Could you try again in bright, even light, facing the camera?"}, code=422)
                # consultation answers (user-reported) are combined with what the photo shows
                prof = {"skin_type": a.get("skin_type") if a.get("skin_type") in skin.SKIN_TYPES else (feel.get("skin_type") or None),
                        "concerns": list(dict.fromkeys(a.get("concerns", []) + [c for c in feel.get("concerns", []) if c in skin.CONCERNS])),
                        "avoid": feel.get("avoid", [])}
                r = skin.recommend(bot.con, prof); st_ = self._state()
                if r["profile"].get("skin_type"): st_["skin"] = r["profile"]["skin_type"]
                st_["focus"] = r["focus"]; r["suggestions"] = bot.suggest("", r["profile"] | {"focus": r["focus"], "top_ingredients": r.get("top_ingredients")})
                return self._send({"analysis": a, "deleted": True, **r})
        except RuntimeError as e:
            if str(e) == "NO_KEY": return self._send({"error": "Photo skin checks aren't available right now. The quick quiz will give you personalised picks in the meantime."}, code=503)
            return self._send({"error": "Sorry, something went wrong. Please try again."}, code=500)
        except urllib.error.HTTPError as e:
            try: msg = json.load(e)["error"]["message"]
            except Exception: msg = ""
            print(f"[analyze] {skin.provider()} API error {e.code}: {msg[:200]}", file=sys.stderr, flush=True)
            hint = {401: "The API key was rejected.", 429: "Quota or rate limit reached — check billing/credits.",
                    404: "That model isn't available to this key."}.get(e.code, "The provider returned an error.")
            return self._send({"error": "Sorry, the skin check isn't available right now. Please try the quick quiz instead."}, code=502)
        except Exception as e:
            print(f"[analyze] {type(e).__name__}: {str(e)[:200]}", file=sys.stderr, flush=True)
            return self._send({"error": "Sorry, I couldn't check that photo just now. Please try again, or use the quick quiz."}, code=500)
        self._send({"error": "Not found"}, code=404)

    def log_message(self, *a): pass   # never log request details
print(f"Open http://localhost:{PORT}", flush=True); HTTPServer(("127.0.0.1", PORT), H).serve_forever()
