import os, sys
from src.db import build
from src.answer import Concierge
root = os.path.dirname(os.path.abspath(__file__))
d = os.path.join(root, "data/kaggle") if os.path.exists(os.path.join(root, "data/kaggle/product_info.csv")) else os.path.join(root, "data/sample")
print(f"[data: {d}]"); bot = Concierge(build(os.path.join(root, "sephora.db"), d))
if len(sys.argv) > 1: print(bot.ask(" ".join(sys.argv[1:]))); sys.exit()
while (q := input("you> ").strip()) not in ("", "quit"): print(bot.ask(q), "\n")
