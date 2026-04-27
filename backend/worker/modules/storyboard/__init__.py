"""Storyboard planning layer for AI video generation.

Converts narration blocks into concrete storyboard scenes that describe
specific visual moments rather than generic category templates.

Flow:
    narration blocks → storyboard planner → StoryboardScene list
                     → [quality scoring + rewrite] (optional)
                     → build_prompt_from_storyboard_scene()
                     → AI image generation

Public API:
    StoryboardScene        – dataclass for a single visual scene.
    plan_storyboard()      – main entry point; returns list[StoryboardScene].
    build_prompt_from_storyboard_scene() – converts a scene to a final prompt.
    validate_and_improve_storyboard()    – score and rewrite low-quality scenes.
    compute_scene_similarity()           – similarity score between two scenes.
"""
from worker.modules.storyboard.models import StoryboardScene
from worker.modules.storyboard.planner import plan_storyboard
from worker.modules.storyboard.planner import build_prompt_from_storyboard_scene
from worker.modules.storyboard.quality import validate_and_improve_storyboard
from worker.modules.storyboard.quality import compute_scene_similarity

__all__ = [
    "StoryboardScene",
    "plan_storyboard",
    "build_prompt_from_storyboard_scene",
    "validate_and_improve_storyboard",
    "compute_scene_similarity",
]
