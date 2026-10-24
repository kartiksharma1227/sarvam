from app.agents.llm import LLM
from app.agents.prompting import as_json, load_prompt
from app.pipeline.validate import check_script
from app.schemas.plan import LessonPlan
from app.schemas.script import Script


async def write_script(llm: LLM, plan: LessonPlan) -> Script:
    user = f"Lesson plan:\n{as_json(plan.model_dump())}\n\nWrite the narration for every scene."
    return await llm.structured(
        agent="scriptwriter",
        tier="main",
        system=load_prompt("scriptwriter"),
        user=user,
        output_model=Script,
        check=lambda script: check_script(script, plan),
    )
