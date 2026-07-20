"""
agent_service.py

A simple multi-step "research agent": given a question, it searches the
web, asks the model whether it has enough information yet, runs follow-up
searches if not (up to a step cap), then synthesizes everything into one
final answer.

Deliberately uses plain line-based decisions ("READY" / "SEARCH: ...")
rather than JSON — the Crypto Analyzer's JSON-parsing bugs earlier proved
that free-form JSON from an LLM is fragile (raw newlines, truncation,
markdown fences all break it). A single keyword-per-line format is far
more robust and doesn't need a parser at all, just string checks.

No new cost: this reuses the same free web_search_service.py and the same
generate_response() call your regular chat already uses — just called
more than once per user question, in a loop.
"""

from typing import Optional

from app.services.web_search_service import search_web, format_search_results_for_prompt
from app.services.ai_service import generate_response

MAX_SEARCH_STEPS = 3          # hard cap on total searches per research task
MAX_FOLLOWUPS_PER_ROUND = 2   # cap on how many new searches one "decide" round can request


def run_research_agent(query: str, model: Optional[str] = None) -> dict:
    """Run a bounded multi-step research loop and return a final answer.

    Returns:
        {
            "answer": str,           # the final synthesized answer
            "steps": list[dict],     # a transparent log of what the agent did
            "sources": list[str],    # every unique URL it pulled from
            "search_count": int,     # how many searches it actually ran
        }
    """
    steps: list[dict] = []
    all_results: list[dict] = []

    # Step 1: initial search on the question as-asked.
    initial_results = search_web(query, max_results=5)
    all_results.extend(initial_results)
    steps.append({"action": "search", "query": query, "result_count": len(initial_results)})

    search_count = 1
    context = format_search_results_for_prompt(all_results, query) or "No results found yet."

    # Steps 2+: let the model decide if it needs more searches, up to the cap.
    while search_count < MAX_SEARCH_STEPS:
        decision_prompt = (
            f'You are researching this question: "{query}"\n\n'
            f"Here is what has been found so far:\n{context}\n\n"
            "Do you already have enough information to write a thorough, well-supported answer?\n"
            "- If YES, respond with exactly one word: READY\n"
            "- If NO, respond with 1-2 specific follow-up search queries that would fill in the "
            'missing gaps, one per line, each starting with "SEARCH: " '
            '(example: "SEARCH: Tesla Q2 2026 earnings report")\n\n'
            'Respond with ONLY "READY" or the SEARCH lines — no other text, no explanation.'
        )

        decision = generate_response(decision_prompt, model=model)
        steps.append({"action": "decide", "response": decision.strip()})

        follow_up_queries = [
            line.split("SEARCH:", 1)[1].strip()
            for line in decision.split("\n")
            if line.strip().upper().startswith("SEARCH:")
        ]

        if not follow_up_queries:
            # Either it said READY, or gave an unparseable response — either
            # way, stop searching and move to synthesis rather than looping.
            break

        for fq in follow_up_queries[:MAX_FOLLOWUPS_PER_ROUND]:
            if search_count >= MAX_SEARCH_STEPS:
                break
            fq_results = search_web(fq, max_results=4)
            all_results.extend(fq_results)
            steps.append({"action": "search", "query": fq, "result_count": len(fq_results)})
            search_count += 1

        context = format_search_results_for_prompt(all_results, query) or context

    # Final step: synthesize everything gathered into one coherent answer.
    synthesis_prompt = (
        f'Based on the research below, write a thorough, well-organized answer to: "{query}"\n\n'
        f"{context}\n\n"
        "Use clear markdown formatting with headers where it helps readability. "
        "Cite sources naturally in your writing (e.g. \"according to [source]\"). "
        "If the research doesn't fully answer some part of the question, say so honestly "
        "rather than filling the gap with a guess."
    )

    final_answer = generate_response(synthesis_prompt, model=model)
    steps.append({"action": "synthesize", "search_rounds_used": search_count})

    sources = list({r["url"] for r in all_results if r.get("url")})

    return {
        "answer": final_answer,
        "steps": steps,
        "sources": sources,
        "search_count": search_count,
    }