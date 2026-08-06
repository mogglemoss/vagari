from tuimapper.model.chain import Chain, Signature
from tuimapper.model.store import Store


def make_store(tmp_path, keep=100) -> Store:
    return Store(base_dir=tmp_path / "state", keep=keep)


def test_commit_and_load_latest(tmp_path):
    store = make_store(tmp_path)
    chain = Chain(name="home")
    chain.root.sigs.append(Signature(sig_id="ABC-123"))
    store.commit(chain)

    loaded = store.load_latest("home")
    assert loaded is not None
    assert loaded.root.find_sig("ABC") is not None
    assert store.load_latest("nope") is None


def test_undo_redo(tmp_path):
    store = make_store(tmp_path)
    chain = Chain(name="home")
    store.commit(chain)                                   # snap 1: empty

    chain.root.sigs.append(Signature(sig_id="ABC-123"))
    store.commit(chain)                                   # snap 2: one sig

    undone = store.undo("home")
    assert undone.root.sigs == []

    redone = store.redo("home")
    assert redone.root.find_sig("ABC") is not None

    assert store.redo("home") is None   # nothing newer
    store.undo("home")
    assert store.undo("home") is None   # nothing older


def test_commit_after_undo_truncates_redo_tail(tmp_path):
    store = make_store(tmp_path)
    chain = Chain(name="home")
    store.commit(chain)

    chain.root.sigs.append(Signature(sig_id="ABC-123"))
    store.commit(chain)

    fresh = store.undo("home")                            # back to empty
    fresh.root.sigs.append(Signature(sig_id="XYZ-999"))
    store.commit(fresh)                                   # new branch of history

    assert store.redo("home") is None                     # old future is gone
    assert store.load_latest("home").root.find_sig("XYZ") is not None


def test_prune_keeps_recent(tmp_path):
    store = make_store(tmp_path, keep=3)
    chain = Chain(name="home")
    for i in range(10):
        chain.root.sigs.append(Signature(sig_id=f"AB{chr(ord('A') + i)}-001"))
        store.commit(chain)

    snap_files = list((tmp_path / "state" / "home").glob("snap-*.json"))
    assert len(snap_files) == 3
    assert store.load_latest("home") is not None


def test_chains_listing(tmp_path):
    store = make_store(tmp_path)
    store.commit(Chain(name="home"))
    store.commit(Chain(name="staging"))
    assert store.chains() == ["home", "staging"]
