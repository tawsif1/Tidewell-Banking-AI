import yaml
from rag import vo, EMBED_MODEL, top_matches
from tools import MIN_SEARCH_SCORE

with open("evals/retrieval_questions.yaml", encoding="utf-8") as f:
    questions = yaml.safe_load(f)

not_covered = sum(1 for q in questions if not q["expect"])
print(f"{len(questions)} questions, {not_covered} not covered")

texts = [q["q"] for q in questions]
result = vo.embed(texts, model=EMBED_MODEL, input_type="query")

print(len(result.embeddings), "embeddings")

covered = [(q, emb) for q, emb in zip(questions, result.embeddings) if q["expect"]]
not_covered_q = [(q, emb) for q, emb in zip(questions, result.embeddings) if not q["expect"]]

hit1 = hit5 = usable5 = leaked = 0

for q, emb in covered:
    # steps 1–4 here; add 1 to hit1 / hit5 when they're true
    rows = top_matches(emb, k=5)
    articles = [r["source"].removesuffix(".md") for r in rows]
    scores = [r["score"] for r in rows]

    if articles[0] in q["expect"]:
        hit1 += 1

    if any(a in q["expect"] for a in articles):
        hit5 += 1

    usable = any(a in q["expect"] and score >= MIN_SEARCH_SCORE for a, score in zip(articles, scores))

    if usable:
        usable5 += 1

for q, emb in not_covered_q:
    rows = top_matches(emb, k=5)
    articles = [r["source"].removesuffix(".md") for r in rows]
    scores = [r["score"] for r in rows]

    unusable = any(score >= MIN_SEARCH_SCORE for score in  scores)
    
    if unusable:
        leaked += 1
    

    

    
print(f"hit@1: {hit1}/{len(covered)} = {hit1 / len(covered):.0%}")
print(f"hit@5: {hit5}/{len(covered)} = {hit5 / len(covered):.0%}")
print(f"usable hit@5: {usable5}/{len(covered)} = {usable5 / len(covered):.0%}")
print(f"rejected: {len(not_covered_q) - leaked}/{len(not_covered_q)}")