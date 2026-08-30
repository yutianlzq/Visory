from __future__ import annotations

from src.schemas.platform import TaskState


class InvalidTaskTransition(ValueError):
    def __init__(self, source: TaskState, target: TaskState) -> None:
        self.error_code = "TASK_STATE_TRANSITION_INVALID"
        self.source = source
        self.target = target
        super().__init__(f"invalid task transition: {source.value} -> {target.value}")


_ALLOWED_TRANSITIONS = frozenset(
    {
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
    }
)


def validate_task_transition(source: TaskState, target: TaskState) -> None:
    if (source, target) not in _ALLOWED_TRANSITIONS:
        raise InvalidTaskTransition(source, target)


__all__ = ["InvalidTaskTransition", "validate_task_transition"]
