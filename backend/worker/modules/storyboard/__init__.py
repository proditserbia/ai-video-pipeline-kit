"""Storyboard planning layer for AI video generation.

Converts narration blocks into concrete storyboard scenes that describe
specific visual moments rather than generic category templates.

Flow:
    narration blocks → storyboard planner → StoryboardScene list
                     → build_prompt_from_storyboard_scene()
                     → AI image generation

Public API:
    StoryboardScene        – dataclass for a single visual scene.
    plan_storyboard()      – main entry point; returns list[StoryboardScene].
    build_prompt_from_storyboard_scene() – converts a scene to a final prompt.
"""
from worker.modules.storyboard.models import StoryboardScene
from worker.modules.storyboard.planner import plan_storyboard
from worker.modules.storyboard.planner import build_prompt_from_storyboard_scene

__all__ = [
    "StoryboardScene",
    "plan_storyboard",
    "build_prompt_from_storyboard_scene",
]
