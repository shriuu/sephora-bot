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
    def test_medical(self): self.assertIn("can't say whether", self.b.ask("Is it safe for my eczema?"))
    def test_policy(self): self.assertIn("returns, shipping", self.b.ask("What is the return policy?"))
    def test_reviews(self): self.assertIn("customers", self.b.ask("What are customers saying about Glow Niacinamide Serum?"))
    def test_compare(self): self.assertIn("compare", self.b.ask("difference between Barrier Cream Moisturizer and Light Gel Moisturizer"))
    def test_unknown(self): self.assertIn("couldn't find", self.b.ask("tell me about Zzz Lipstick"))
    def test_smalltalk(self): self.assertIn("Hi there", self.rich("hello")["text"])
    def test_yes_followup(self):
        st = {}; self.rich("What does niacinamide do?", st)
        r = self.rich("yes please", st); self.assertTrue(r["products"])
    def test_asks_skin_type(self):
        st = {}; self.assertIn("skin type", self.rich("recommend something", st)["text"])
        self.assertTrue(self.rich("dry", st)["products"])
if __name__ == "__main__": unittest.main()
