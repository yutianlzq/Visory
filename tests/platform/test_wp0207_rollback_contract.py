from alembic.script import ScriptDirectory
from alembic.script.revision import ResolutionError, Revision, RevisionMap
import pytest

from src.repositories.platform.migrations import _alembic_config


def test_applied_0014_requires_retained_migration_history():
    applied = "0014_wp0207_source_binding"
    scripts = ScriptDirectory.from_config(_alembic_config())
    # 只演练已应用的 main 0014 历史前缀；追加 merge head 不改变该回滚契约。
    revisions = tuple(scripts.walk_revisions(head=applied))

    def history(keep_applied):
        return RevisionMap(lambda: iter(
            Revision(item.revision, item.down_revision, item.dependencies, item.branch_labels)
            for item in revisions if keep_applied or item.revision != applied
        ))

    retained = history(True)
    assert retained.get_revision(applied).down_revision == "0013_wp0302_feature_store"
    assert retained.heads == (applied,)
    removed = history(False)
    assert removed.heads == ("0013_wp0302_feature_store",)
    with pytest.raises(ResolutionError):
        removed.get_revision(applied)
