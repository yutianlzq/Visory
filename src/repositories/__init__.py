# -*- coding: utf-8 -*-
"""
===================================
数据访问层模块初始化
===================================

职责：
1. 兼容导出 Legacy Repository 类
2. 避免导入子包时提前加载整个 Legacy 数据与配置链
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_REPOSITORY_EXPORTS = {
    "AnalysisRepository": ("src.repositories.analysis_repo", "AnalysisRepository"),
    "BacktestRepository": ("src.repositories.backtest_repo", "BacktestRepository"),
    "DecisionSignalRepository": ("src.repositories.decision_signal_repo", "DecisionSignalRepository"),
    "DecisionSignalOutcomeRepository": (
        "src.repositories.decision_signal_outcome_repo",
        "DecisionSignalOutcomeRepository",
    ),
    "StockRepository": ("src.repositories.stock_repo", "StockRepository"),
    "SkillOpinionSampleRepository": (
        "src.repositories.skill_opinion_sample_repo",
        "SkillOpinionSampleRepository",
    ),
}

__all__ = list(_REPOSITORY_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _REPOSITORY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
