"""
agent.py

Exposes the research agent (agent_service.py) as an API endpoint. This is
deliberately a separate, one-shot request/response endpoint rather than a
streaming one — the agent may take a few seconds longer than a normal chat
message since it can run multiple searches internally before responding,
so the frontend should show a "researching..." state rather than expecting
instant tokens.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.users import get_current_user
from app.models.user import User
from app.services.agent_service import run_research_agent

router = APIRouter(prefix="/agent", tags=["Research Agent"])


class ResearchRequest(BaseModel):
    query: str
    model: Optional[str] = "swift"  # "swift" (Groq/Llama) or "nova" (Gemini)


class ResearchStep(BaseModel):
    action: str
    query: Optional[str] = None
    result_count: Optional[int] = None
    response: Optional[str] = None
    search_rounds_used: Optional[int] = None


class ResearchResponse(BaseModel):
    answer: str
    steps: list[ResearchStep]
    sources: list[str]
    search_count: int


@router.post("/research", response_model=ResearchResponse)
def research(
    request: ResearchRequest,
    current_user: User = Depends(get_current_user),
):
    """Run a bounded multi-step research task: search, decide if more
    searching is needed, repeat up to a cap, then synthesize a final answer."""

    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        result = run_research_agent(request.query.strip(), model=request.model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research agent failed: {str(e)}")

    return ResearchResponse(**result)