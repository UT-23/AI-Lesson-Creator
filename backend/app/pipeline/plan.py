"""Step `plan`: objective → atomic outcomes + research sub-queries."""

from typing import Any

from app.pipeline.context import StepContext
from app.providers.llm import generate_structured
from app.schemas import ResearchPlan

PLAN_SYSTEM = (
    "You are an instructional designer planning research for a single lesson of at most 45 minutes. "
    "Be precise and do not invent facts."
)


def build_plan_prompt(title: str, objective: str) -> str:
    return f"""Plan the research for this lesson.

TITLE: {title}
OBJECTIVE: {objective}

1. Decompose the objective into atomic learning outcomes.
   - Each outcome has exactly one action verb and one concept.
   - Keep the objective's own verbs (e.g. "explain", "distinguish", "calculate"); do not swap them for weaker ones.
   - Cover everything in the objective and nothing beyond it.
2. Write 4-8 web search sub-queries that together gather evidence for every outcome.
   - At least two queries must name an authoritative source type for this subject, e.g. the standard or
     official documentation (RFC, MDN) for technology; a government regulator or central bank (.gov,
     investor education) for finance; a university or open textbook for maths and science.
   - Include at least one query aimed at a worked example or common misconceptions.
3. Write 1-2 short book-catalogue queries (2-4 words) naming the subject itself, the way a library
   catalogue would index it (e.g. "HTTP protocol", "compound interest"). Not the lesson title.

Return JSON with keys "outcomes", "queries" and "book_queries"."""


def run_plan(ctx: StepContext) -> dict[str, Any]:
    plan = generate_structured(
        ctx.providers.gen_llm,
        build_plan_prompt(ctx.lesson.title, ctx.lesson.objective),
        ResearchPlan,
        system=PLAN_SYSTEM,
        max_repairs=ctx.settings.llm_max_repairs,
    )
    return plan.model_dump()
