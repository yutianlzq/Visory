from __future__ import annotations

import pytest

from src.core.platform.task_state_machine import InvalidTaskTransition, validate_task_transition
from src.schemas.platform import TaskState


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TaskState.ACCEPTED, TaskState.QUEUED),
        (TaskState.QUEUED, TaskState.LEASED),
        (TaskState.LEASED, TaskState.RUNNING),
        (TaskState.RUNNING, TaskState.SUCCEEDED),
        (TaskState.RUNNING, TaskState.DEGRADED),
        (TaskState.RUNNING, TaskState.FAILED),
        (TaskState.RUNNING, TaskState.CANCELLED),
        (TaskState.RUNNING, TaskState.RETRY_WAIT),
        (TaskState.RETRY_WAIT, TaskState.QUEUED),
        (TaskState.QUEUED, TaskState.BLOCKED),
        (TaskState.RUNNING, TaskState.BLOCKED),
        (TaskState.BLOCKED, TaskState.QUEUED),
        (TaskState.BLOCKED, TaskState.CANCELLED),
        (TaskState.QUEUED, TaskState.CANCELLED),
    ],
)
def test_documented_task_state_transitions_are_allowed(source: TaskState, target: TaskState) -> None:
    validate_task_transition(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TaskState.ACCEPTED, TaskState.RUNNING),
        (TaskState.QUEUED, TaskState.SUCCEEDED),
        (TaskState.LEASED, TaskState.QUEUED),
        (TaskState.SUCCEEDED, TaskState.QUEUED),
        (TaskState.FAILED, TaskState.RUNNING),
        (TaskState.CANCELLED, TaskState.QUEUED),
        (TaskState.RUNNING, TaskState.RUNNING),
    ],
)
def test_undocumented_task_state_transitions_are_rejected(source: TaskState, target: TaskState) -> None:
    with pytest.raises(InvalidTaskTransition) as captured:
        validate_task_transition(source, target)
    assert captured.value.error_code == "TASK_STATE_TRANSITION_INVALID"
