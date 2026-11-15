import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.db import build; from src.answer import Concierge
S = os.path.join(os.path.dirname(__file__), "../data/sample")
class T(unittest.TestCase):
    @classmethod
    def setUpClass(c): c.b = Concierge(build("/tmp/t.db", S))
    def rich(self, q, st=None): return self.b.ask_rich(q, st if st is not None else {})
    def test_ingredient(self):
        r = self.rich("Which products contain niacinamide?")
        self.assertIn("Glow Niacinamide Serum", [p["name"] for p in r["products"]])
    def test_medical(self): self.assertIn("dermatologist", self.b.ask("Is it safe for my eczema?"))
    def test_policy(self): self.assertIn("returns, shipping", self.b.ask("What is the return policy?"))
    def test_reviews(self):
        r = self.rich("What are customers saying about Glow Niacinamide Serum?")
        self.assertEqual(r["detail"]["name"], "Glow Niacinamide Serum"); self.assertTrue(r["detail"]["reviews"])
    def test_compare(self): self.assertIn("Barrier Cream Moisturizer", self.b.ask("difference between Barrier Cream Moisturizer and Light Gel Moisturizer"))
    def test_unknown(self):
        r = self.rich("tell me about Zzz Lipstick"); self.assertFalse(r["products"]); self.assertNotIn("detail", r)
    def test_smalltalk(self): self.assertTrue(len(self.rich("hello")["text"]) > 20)
    def test_yes_followup(self):
        st = {}; self.rich("What does niacinamide do?", st)
        r = self.rich("yes please", st); self.assertTrue(r["products"])
    def test_asks_skin_type(self):
        st = {}; self.assertIn("skin type", self.rich("recommend something", st)["text"])
        self.assertTrue(self.rich("dry", st)["products"])
    def test_typo_did_you_mean(self):
        st = {}; r = self.rich("what does niacinamde do?", st)
        self.assertEqual(r.get("didyoumean"), "what does niacinamide do?")
        r2 = self.rich("yes", st); self.assertNotIn("didyoumean", r2); self.assertIn("niacinamide", r2["text"].lower())
    def test_no_false_did_you_mean(self):
        for q in ("What does niacinamide do?", "I have dry skin", "hello", "which products contain niacinamide?"):
            self.assertNotIn("didyoumean", self.rich(q))
if __name__ == "__main__": unittest.main()
