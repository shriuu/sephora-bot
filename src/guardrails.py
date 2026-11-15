"""Guardrails: medical-claim refusal, scope, disclaimers."""
import re

MEDICAL = re.compile(r"\b(safe for (my|me)|cure|treat|diagnos|eczema|rosacea|psoriasis|dermatitis|"
                     r"pregnan|allerg|prescription|infection)\b", re.I)
POLICY = re.compile(r"\b(return|refund|exchange|shipping|delivery|authentic|sample)s?\b", re.I)

MEDICAL_NOTE = ("I can't say whether something is safe for a skin condition or an allergy. That's one for a dermatologist or "
                "pharmacist. What I can do is show you what's in a product and what other customers have said. "
                "And please patch-test anything new first.")
POLICY_NOTE = ("I don't have access to returns, shipping or order policies, and I'd hate to give you the wrong information. "
               "The Sephora help page for your region will have the latest. I'm happy to help with products and ingredients, though!")
DATA_NOTE = ""

def is_medical(q): return bool(MEDICAL.search(q))
def is_policy(q): return bool(POLICY.search(q))
