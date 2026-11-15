# Sephora Beauty Concierge (Option A: Product & Ingredient Knowledge)

Stdlib-only prototype: SQLite (products, ingredients, reviews) + BM25 over reviews + rule-based router + guardrails.

- Run: `python3 cli.py "Which products contain niacinamide?"` (or no args for chat)
- Test: `python3 -m unittest discover -s tests`
- Real data: put the Kaggle files (`product_info.csv`, `reviews_*.csv`) in `data/kaggle/`; otherwise bundled demo data in `data/sample/` (synthetic) is used.
- Guardrails: no medical advice, reviews labelled as opinions, no policy guessing, 2023 data disclaimer.
- Next: swap BM25 for embeddings, add an LLM generation step over the retrieved facts.

## On-device photo analysis (no API key, photo never leaves your computer)
1. Install Ollama from https://ollama.com (or `brew install ollama`) and start it.
2. `ollama pull qwen2.5vl:7b`  (about 6 GB; fine on 16 GB+ Macs). Use another vision model with `LOCAL_VISION_MODEL=<name>`.
3. `python3 server.py` — the consent box will say "100% on-device".
Cloud analysis (OpenAI/Anthropic) is OFF unless you set `ALLOW_CLOUD_VISION=1` plus a key.
