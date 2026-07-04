import pytest

from src.storage.log_store import LocalLogStore


@pytest.fixture
def store(tmp_path):
    return LocalLogStore(root=str(tmp_path / "logs"))


def test_write_and_read_roundtrip(store):
    ref = store.write_text("runs/run-1/stdout.txt", "hello world")
    assert ref == "local://runs/run-1/stdout.txt"
    assert store.read_text(ref) == "hello world"


def test_read_missing_raises(store):
    with pytest.raises(FileNotFoundError):
        store.read_text("local://missing.txt")