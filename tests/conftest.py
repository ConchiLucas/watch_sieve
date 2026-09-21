import pytest

from watch_sieve.store import MemoryTopicStore, set_store


@pytest.fixture(autouse=True)
def memory_store(request, monkeypatch):
    if request.node.get_closest_marker("postgres"):
        yield None
        return
    store = MemoryTopicStore()
    set_store(store)
    monkeypatch.setattr("watch_sieve.titles.get_store", lambda: store)
    yield store
    set_store(None)
