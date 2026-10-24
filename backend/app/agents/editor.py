from app.agents.llm import LLM
from app.agents.prompting import as_json, load_prompt
from app.pipeline.validate import check_script
from app.schemas.plan import LessonPlan
from app.schemas.script import Script


async def edit_script(llm: LLM, plan: LessonPlan, draft: Script) -> Script:
    user = (
        f"Lesson plan (each scene's layout is fixed):\n{as_json(plan.model_dump())}\n\n"
        f"Draft narration:\n{as_json(draft.model_dump())}\n\n"
        "Return the edited narration for every scene."
    )
    return await llm.structured(
        agent="editor",
        tier="main",
        system=load_prompt("editor"),
        user=user,
        output_model=Script,
        check=lambda script: check_script(script, plan),
    )
