from app.agents.llm import LLM
from app.agents.prompting import fill, load_prompt
from app.pipeline.validate import check_plan
from app.schemas.plan import LessonPlan


async def plan_lesson(llm: LLM, topic: str) -> LessonPlan:
    system = fill(load_prompt("planner"), layouts=load_prompt("layouts"))
    user = f"Topic: {topic}\n\nPlan the lesson."
    return await llm.structured(
        agent="planner",
        tier="main",
        system=system,
        user=user,
        output_model=LessonPlan,
        check=check_plan,
    )
