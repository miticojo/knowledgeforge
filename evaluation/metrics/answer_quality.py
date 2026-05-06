"""L3: Answer Quality Metrics via LLM-as-Judge.

Uses Gemini to evaluate the Coordinator's final answers on:
- Faithfulness: Is the answer grounded in retrieved context (no hallucination)?
- Answer Relevancy: Does the answer address the question?
- Answer Correctness: Does the answer match expected ground truth?

Uses LLM-as-judge pattern (no RAGAS dependency for simplicity — can be swapped in).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "kb-agent"))


def load_eval_questions() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "ground_truth", "eval_questions.json")
    with open(path) as f:
        return json.load(f)


def get_coordinator_answer(question: str) -> tuple[str, list[str]]:
    """Get the Coordinator's answer and retrieved chunks for a question."""
    from agents.search import tool_query_spanner_graph
    result = json.loads(tool_query_spanner_graph(question))
    chunks = result.get("semantically_similar_chunks", [])

    # Simulate Coordinator: for eval purposes, use a direct LLM call
    # with the same instruction as the Coordinator
    from google import genai
    client = genai.Client()

    # Number each chunk for citation
    numbered_chunks = []
    for i, c in enumerate(chunks[:15]):
        numbered_chunks.append(f"[Chunk {i+1}/{min(len(chunks),15)}]\n{c}")
    context = "\n\n---\n\n".join(numbered_chunks)

    prompt = f"""You MUST answer based ONLY on the following context chunks.

Follow these 3 steps:
STEP 1 — EXTRACT: Read EVERY chunk below. For each, extract ALL facts relevant to the question.
STEP 2 — SYNTHESIZE: Combine extracted facts into a complete answer. Include ALL relevant details from ALL chunks.
STEP 3 — VERIFY: Re-check that you included facts from every relevant chunk. Do NOT say "information not available" if any chunk contains relevant content.

CONTEXT:
{context}

QUESTION: {question}

ANSWER (be thorough and complete):"""

    # Answer generator: configurable via env var, default gemini-2.5-flash
    _ANSWER_MODEL = os.environ.get("EVAL_ANSWER_MODEL", "gemini-2.5-flash")
    if "gemini-3" in _ANSWER_MODEL:
        _answer_config = genai.types.GenerateContentConfig(
            temperature=0.1,
            thinking_config=genai.types.ThinkingConfig(thinking_level="LOW"),
        )
    else:
        _answer_config = genai.types.GenerateContentConfig(
            temperature=0.1,
            thinking_config=genai.types.ThinkingConfig(thinking_budget=4096),
        )
    response = client.models.generate_content(
        model=_ANSWER_MODEL,
        contents=prompt,
        config=_answer_config,
    )
    answer = response.text if response.text else ""
    return answer, chunks


def judge_with_llm(question: str, answer: str, expected: str, context_chunks: list[str]) -> dict:
    """Use Gemini as judge to evaluate answer quality."""
    from google import genai
    client = genai.Client()

    context_text = "\n".join(context_chunks[:5])

    judge_prompt = f"""You are an evaluation judge. Score the following answer on 3 dimensions.
Return ONLY a JSON object with scores 0-5 and brief justifications.

QUESTION: {question}

EXPECTED ANSWER: {expected}

ACTUAL ANSWER: {answer}

RETRIEVED CONTEXT (first 5 chunks):
{context_text[:3000]}

Score these dimensions (0=terrible, 5=perfect):
1. faithfulness: Is the answer grounded in the retrieved context? (no hallucination)
2. relevancy: Does the answer address the question asked?
3. correctness: Does the answer convey the same information as the expected answer?

Return JSON: {{"faithfulness": {{"score": N, "reason": "..."}}, "relevancy": {{"score": N, "reason": "..."}}, "correctness": {{"score": N, "reason": "..."}}}}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=judge_prompt,
    )
    text = response.text or ""
    # Extract JSON from response
    try:
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        return {
            "faithfulness": {"score": -1, "reason": "Parse error"},
            "relevancy": {"score": -1, "reason": "Parse error"},
            "correctness": {"score": -1, "reason": "Parse error"},
        }


def run():
    """Run L3 evaluation."""
    questions = load_eval_questions()
    results = []

    for q in questions:
        print(f"  [{q['id']}] {q['question'][:60]}...", end=" ", flush=True)

        try:
            answer, chunks = get_coordinator_answer(q["question"])
            scores = judge_with_llm(q["question"], answer, q["expected_answer"], chunks)

            result = {
                "id": q["id"],
                "category": q["category"],
                "question": q["question"],
                "answer_preview": answer[:200],
                "chunks_used": len(chunks),
                "scores": scores,
            }
            results.append(result)

            f = scores.get("faithfulness", {}).get("score", -1)
            r = scores.get("relevancy", {}).get("score", -1)
            c = scores.get("correctness", {}).get("score", -1)
            print(f"F={f}/5 R={r}/5 C={c}/5")

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "id": q["id"],
                "category": q["category"],
                "error": str(e),
            })

    # Aggregate
    valid = [r for r in results if "scores" in r]
    if valid:
        avg_faith = sum(r["scores"]["faithfulness"]["score"] for r in valid if r["scores"]["faithfulness"]["score"] >= 0) / len(valid)
        avg_rel = sum(r["scores"]["relevancy"]["score"] for r in valid if r["scores"]["relevancy"]["score"] >= 0) / len(valid)
        avg_corr = sum(r["scores"]["correctness"]["score"] for r in valid if r["scores"]["correctness"]["score"] >= 0) / len(valid)
    else:
        avg_faith = avg_rel = avg_corr = 0

    return {
        "layer": "L3_Answer_Quality",
        "per_question": results,
        "aggregates": {
            "avg_faithfulness": round(avg_faith, 2),
            "avg_relevancy": round(avg_rel, 2),
            "avg_correctness": round(avg_corr, 2),
            "overall_score": round((avg_faith + avg_rel + avg_corr) / 3, 2),
            "evaluated": len(valid),
            "errors": len(results) - len(valid),
        },
    }


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
