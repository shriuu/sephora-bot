"""Load product/review CSVs (Kaggle schema) into SQLite."""
import re, warnings, ast, csv, glob, os, sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(product_id TEXT PRIMARY KEY, name TEXT, brand TEXT,
  rating REAL, n_reviews INTEGER, price_usd REAL, category TEXT, subcategory TEXT, highlights TEXT, tertiary TEXT, shade TEXT, shade_desc TEXT);
CREATE TABLE IF NOT EXISTS ingredients(product_id TEXT, ingredient TEXT);
CREATE INDEX IF NOT EXISTS ing_idx ON ingredients(ingredient COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS reviews(product_id TEXT, rating REAL, recommended REAL,
  title TEXT, text TEXT, skin_type TEXT, skin_tone TEXT);
CREATE INDEX IF NOT EXISTS rev_idx ON reviews(product_id);
"""

def _f(v, cast=float):
    try: return cast(v)
    except (TypeError, ValueError): return None

_SPLIT = re.compile(r",\s+(?![^()]*\))")   # commas not inside parentheses


def _list(s):
    """Kaggle stores ingredients as a Python list whose items are often one long comma-separated string."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore"); v = ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return []
    if not isinstance(v, list): return []
    out = []
    for item in v:
        item = str(item).strip()
        if item.endswith(":") or not item: continue          # section headers like 'Capri Eau de Parfum:'
        out += [x.strip(" .") for x in _SPLIT.split(item) if x.strip(" .")]
    return out


def build(db_path, data_dir):
    if os.path.exists(db_path): os.remove(db_path)
    con = sqlite3.connect(db_path); con.executescript(SCHEMA)
    with open(os.path.join(data_dir, "product_info.csv"), newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            con.execute("INSERT OR REPLACE INTO products VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                r["product_id"], r["product_name"], r["brand_name"], _f(r.get("rating")),
                _f(r.get("reviews"), lambda x: int(float(x))), _f(r.get("price_usd")),
                r.get("primary_category"), r.get("secondary_category"), r.get("highlights"),
                r.get("tertiary_category"), r.get("variation_value"), r.get("variation_desc")))
            con.executemany("INSERT INTO ingredients VALUES(?,?)",
                            [(r["product_id"], i) for i in _list(r.get("ingredients", ""))])
    for path in sorted(glob.glob(os.path.join(data_dir, "reviews*.csv"))):
        with open(path, newline="", encoding="utf-8") as fh:
            con.executemany("INSERT INTO reviews VALUES(?,?,?,?,?,?,?)", [(
                r["product_id"], _f(r.get("rating")), _f(r.get("is_recommended")),
                r.get("review_title"), r.get("review_text"), r.get("skin_type"), r.get("skin_tone"))
                for r in csv.DictReader(fh)])
    con.commit(); return con
