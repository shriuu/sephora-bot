"""Minimal BM25 over review text (stdlib only)."""
import math, re
from collections import Counter

def tok(s): return re.findall(r"[a-z0-9]+", (s or "").lower())

class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [Counter(tok(d["text"])) for d in docs]; self.meta = docs
        self.len = [sum(c.values()) for c in self.docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0
        self.df = Counter(t for c in self.docs for t in c)
        self.k1, self.b = k1, b

    def search(self, query, k=5, filt=None):
        q, n, out = tok(query), len(self.docs), []
        for i, c in enumerate(self.docs):
            if filt and not filt(self.meta[i]): continue
            s = 0.0
            for t in q:
                if t in c:
                    idf = math.log(1 + (n - self.df[t] + .5) / (self.df[t] + .5))
                    s += idf * c[t] * (self.k1 + 1) / (c[t] + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            if s > 0: out.append((s, self.meta[i]))
        return [m for _, m in sorted(out, key=lambda x: -x[0])[:k]]
