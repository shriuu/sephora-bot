"""Plain-language guide to common skincare ingredients and product types.
General cosmetic information only (not medical advice). Keys are canonical names; aliases are matched in user text/ingredient lists."""

# name: (aliases, short role, longer description, usually good for, things to know)
INGREDIENTS = {
 "niacinamide": (["niacinamide", "vitamin b3"], "balances oil, evens tone", "A form of vitamin B3 that helps regulate oil, refine the look of pores and fade the look of dark marks.", "oily, combination, blemish-prone, uneven tone", "Very well tolerated; high strengths can tingle for some."),
 "salicylic acid": (["salicylic", "bha"], "unclogs pores", "An oil-soluble exfoliating acid (BHA) that works inside pores to loosen oil and dead skin.", "oily, blemish-prone, blackheads", "Can dry or irritate; start a few times a week and use sunscreen."),
 "glycolic acid": (["glycolic"], "exfoliates, brightens", "A small AHA that dissolves dead surface skin for smoother, brighter-looking skin.", "dullness, rough texture, uneven tone", "Can sting and increases sun sensitivity; use SPF."),
 "lactic acid": (["lactic acid"], "gentle exfoliation + hydration", "A milder AHA that exfoliates while also attracting moisture.", "dullness, dry or sensitive-leaning skin that tolerates exfoliation", "Still an acid: patch test and use SPF."),
 "mandelic acid": (["mandelic"], "gentle brightening exfoliant", "A larger-molecule AHA that exfoliates more slowly and gently.", "dullness, uneven tone, easily irritated skin", "Use sunscreen."),
 "azelaic acid": (["azelaic"], "calms redness, fades marks", "Helps with the look of blemishes, redness and post-blemish marks.", "blemish-prone, redness-prone, uneven tone", "May tingle at first."),
 "benzoyl peroxide": (["benzoyl"], "targets blemish-causing bacteria", "A common over-the-counter blemish ingredient that reduces acne-causing bacteria.", "blemish-prone, oily", "Can dry and bleach fabrics; start low."),
 "retinol": (["retinol", "retinal", "retinyl"], "smooths fine lines and texture", "A vitamin A derivative that speeds up skin renewal, helping the look of fine lines, texture and marks.", "fine lines, uneven texture, dark marks", "Introduce slowly, use at night with SPF by day. Avoid in pregnancy unless your doctor says otherwise."),
 "bakuchiol": (["bakuchiol"], "gentler retinol alternative", "A plant-derived ingredient often used as a softer alternative to retinol.", "fine lines, sensitive skin wanting an anti-ageing step", "Less research than retinol."),
 "peptides": (["peptide"], "supports firm-looking skin", "Short chains of amino acids that signal skin to look firmer and smoother.", "fine lines, loss of firmness", "Generally gentle."),
 "vitamin c": (["vitamin c", "ascorb", "ascorbyl"], "brightens, antioxidant", "An antioxidant that helps protect skin from environmental stress and brighten the look of dark spots.", "dullness, dark spots, dull-looking mature skin", "Can sting; store away from light and air."),
 "hyaluronic acid": (["hyaluronic", "sodium hyaluronate"], "draws in water", "A humectant that holds many times its weight in water, plumping the look of skin.", "all types, especially dehydrated skin", "Works best on damp skin, followed by a moisturiser."),
 "glycerin": (["glycerin"], "basic hydrator", "A classic humectant that pulls moisture into the top layer of skin.", "all skin types", "Very gentle and common."),
 "ceramides": (["ceramide"], "repairs the skin barrier", "Natural skin lipids that help hold moisture in and keep the barrier strong.", "dry, sensitive, barrier-stressed skin", "Generally gentle."),
 "squalane": (["squalane", "squalene"], "lightweight moisturiser", "A light, non-greasy oil that softens and locks in moisture.", "dry, normal, even oily skin", "Usually well tolerated."),
 "panthenol": (["panthenol", "provitamin b5", "vitamin b5"], "soothes and hydrates", "Provitamin B5 that soothes and helps skin hold moisture.", "sensitive, dry, irritated-looking skin", "Gentle."),
 "centella asiatica": (["centella", "cica", "madecassoside"], "calms the look of redness", "A soothing plant extract used in 'cica' products to calm and comfort skin.", "sensitive, redness-prone skin", "Generally gentle."),
 "allantoin": (["allantoin"], "soothes and softens", "A mild skin-conditioning ingredient that calms and smooths.", "sensitive or dry skin", "Gentle."),
 "colloidal oat": (["colloidal oat", "avena"], "soothes dry, itchy-feeling skin", "Finely ground oat that comforts and moisturises.", "dry, sensitive skin", "Gentle."),
 "bisabolol": (["bisabolol"], "calming", "A chamomile-derived ingredient that soothes the look of redness.", "sensitive skin", "Gentle."),
 "zinc": (["zinc pca", "zinc oxide", "zinc"], "oil control / mineral sunscreen", "Zinc PCA helps with oil and blemishes; zinc oxide is a mineral sunscreen filter.", "oily skin; sensitive skin (zinc oxide SPF)", "Zinc oxide can leave a white cast."),
 "tea tree": (["tea tree", "melaleuca"], "blemish-focused", "An essential oil used for its purifying feel in blemish products.", "blemish-prone skin", "Can irritate sensitive skin."),
 "kaolin clay": (["kaolin", "clay", "bentonite"], "absorbs oil", "Mineral clays that soak up excess oil in masks and cleansers.", "oily, congested skin", "Can dry skin if overused."),
 "arbutin": (["arbutin"], "fades dark marks", "A brightening ingredient that helps the look of uneven pigment.", "dark spots, uneven tone", "Use with SPF."),
 "tranexamic acid": (["tranexamic"], "fades discolouration", "A newer brightening ingredient for uneven tone and marks.", "dark spots, melasma-looking patches (see a dermatologist for diagnosis)", "Use with SPF."),
 "fragrance": (["fragrance", "parfum"], "adds scent (can irritate)", "Added for scent, with no skin benefit. A common trigger for sensitive skin.", "n/a", "Choose 'fragrance-free' if your skin is reactive."),
 "sunscreen filters": (["spf", "avobenzone", "octinoxate", "homosalate"], "protects from UV", "Ingredients that block or absorb UV rays, helping prevent sun damage and dark marks.", "everyone, daily", "Reapply every ~2 hours in the sun."),
}

PRODUCT_TYPES = {
 "cleanser": ("Removes dirt, oil, makeup and sunscreen at the start of your routine. Gel/foam suit oily skin; cream/milk suit dry skin.", ["cleanser", "face wash"]),
 "toner": ("Used after cleansing to rebalance or add a treatment step (hydrating or exfoliating, depending on the formula).", ["toner", "essence"]),
 "serum": ("A lightweight, concentrated treatment aimed at a specific concern, such as dark spots, hydration or fine lines. Applied before moisturiser.", ["serum"]),
 "moisturizer": ("Locks in water and supports the skin barrier. Gels are lightest; creams are richer.", ["moisturizer", "moisturiser", "cream", "lotion"]),
 "sunscreen": ("The most important daily step: protects against UV that causes burns, dark spots and early ageing.", ["sunscreen", "spf"]),
 "mask": ("A weekly-ish treatment: clay masks absorb oil, sheet/cream masks hydrate, exfoliating masks smooth.", ["mask"]),
 "eye cream": ("A moisturiser formulated for the thinner eye area; mostly hydrates and can soften the look of fine lines.", ["eye cream", "eye care"]),
 "treatment": ("A targeted product (spot treatment, exfoliant, retinoid) used on a particular concern.", ["treatment", "spot"]),
}

def _norm(s): return (s or "").lower()

def find_ingredient(text):
    t = _norm(text)
    for name, (aliases, *_rest) in INGREDIENTS.items():
        if any(a in t for a in aliases): return name
    return None

def short(keyword):
    k = _norm(keyword)
    for name, (aliases, role, *_r) in INGREDIENTS.items():
        if k == name or any(k in a or a in k for a in aliases): return role
    return None

def explain_ingredient(name):
    aliases, role, desc, good, note = INGREDIENTS[name]
    out = f"{name.title()} in a nutshell: {role}. {desc}"
    if good != "n/a": out += f" It tends to suit {good}."
    if note: out += f" {note}"
    return out + f"\n\nWant me to show you some well-reviewed products with {name}?"

def find_product_type(text):
    t = _norm(text)
    for name, (desc, kws) in PRODUCT_TYPES.items():
        if any(k in t for k in kws): return name
    return None

def explain_type(name): return f"{PRODUCT_TYPES[name][0]}\n\nWant me to pick out a few well-reviewed {name}s for you?"
