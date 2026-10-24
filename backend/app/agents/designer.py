from app.agents.llm import LLM
from app.agents.prompting import as_json, fill, layout_rules, load_prompt
from app.pipeline.validate import check_scene
from app.schemas.plan import LessonPlan, PlannedScene
from app.schemas.scene import designer_output_model


async def design_scene(
    llm: LLM, plan: LessonPlan, planned: PlannedScene, narration: str, icons: list[str]
) -> dict:
    """Returns a full scene spec: {id, title, narration, layout, slots}."""
    output_model = designer_output_model(planned.layout)
    system = fill(
        load_prompt("designer"),
        layout_rules=layout_rules(planned.layout),
        icons=", ".join(icons),
    )
    user = (
        f"Lesson: {plan.title}\n"
        f"Scene {planned.id} ({planned.purpose}), layout: {planned.layout}\n"
        f"Key point: {planned.key_point}\n"
        f"Key numbers: {as_json(planned.key_numbers)}\n\n"
        f"Narration (appear_on phrases must be copied from this exactly):\n{narration}\n\n"
        "Fill in the title and slots."
    )

    def check(design) -> list[str]:
        return check_scene(
            planned.layout, design.slots.model_dump(exclude_none=True), narration
        )

    design = await llm.structured(
        agent=f"designer[{planned.id}]",
        tier="main",
        system=system,
        user=user,
        output_model=output_model,
        check=check,
    )
    return {
        "id": planned.id,
        "title": design.title,
        "narration": narration,
        "layout": planned.layout,
        "slots": design.slots.model_dump(exclude_none=True),
    }
