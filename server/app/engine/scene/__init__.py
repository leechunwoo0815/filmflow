"""Scene DSL v1：声明式、确定性、引擎无关的场景程序。"""
from .compiler import compile_scene, static_program
from .schema import SCENE_SCHEMA, validate_program

__all__ = ["SCENE_SCHEMA", "compile_scene", "static_program", "validate_program"]
