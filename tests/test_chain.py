import pytest

from vagari.model.chain import Chain, ChainError, Signature, SigGroup


def make_chain() -> Chain:
    chain = Chain(name="test")
    chain.root.name = "J105443"
    chain.root.sigs.append(Signature(sig_id="QLM-802", group=SigGroup.WORMHOLE))
    chain.root.sigs.append(Signature(sig_id="FIY-570", group=SigGroup.RELIC))
    return chain


def test_open_and_nav():
    chain = make_chain()
    conn = chain.open_connection("qlm", "J154535", jclass="C1", effect="Black Hole")
    assert conn.child.name == "J154535"

    system = chain.nav("qlm")
    assert system.name == "J154535"
    assert chain.location == ["QLM"]

    chain.up()
    assert chain.current() is chain.root
    chain.nav("QLM")
    chain.top()
    assert chain.location == []


def test_nav_requires_opened_connection():
    chain = make_chain()
    with pytest.raises(ChainError):
        chain.nav("fiy")  # a relic site, not an opened wormhole
    with pytest.raises(ChainError):
        chain.nav("zzz")


def test_open_requires_existing_sig():
    chain = make_chain()
    with pytest.raises(ChainError):
        chain.open_connection("zzz", "J100000")


def test_open_twice_rejected():
    chain = make_chain()
    chain.open_connection("qlm", "J154535")
    with pytest.raises(ChainError):
        chain.open_connection("qlm", "J154535")


def test_label_and_flag():
    chain = make_chain()
    chain.label_sig("fiy", "good relic")
    chain.flag_sig("fiy")
    sig = chain.current().find_sig("FIY")
    assert sig.label == "good relic"
    assert sig.flagged


def test_delete_guard():
    chain = make_chain()
    chain.open_connection("qlm", "J154535")
    chain.nav("qlm")
    chain.current().sigs.append(Signature(sig_id="ABC-001"))
    chain.top()

    with pytest.raises(ChainError):
        chain.delete_sig("qlm")  # child has mapped content

    chain.delete_sig("qlm", force=True)
    assert chain.current().find_sig("qlm") is None
    assert chain.current().find_connection("qlm") is None


def test_delete_leaf_connection_allowed():
    chain = make_chain()
    chain.open_connection("qlm", "J154535")
    chain.delete_sig("qlm")  # empty child: no guard
    assert chain.current().find_connection("qlm") is None


def test_roundtrip_serialisation():
    chain = make_chain()
    chain.open_connection("qlm", "J154535", jclass="C1", statics="N", effect="Black Hole")
    chain.nav("qlm")

    restored = Chain.from_dict(chain.to_dict())
    assert restored.name == "test"
    assert restored.location == ["QLM"]
    assert restored.current().name == "J154535"
    assert restored.current().effect == "Black Hole"
    assert restored.root.find_sig("FIY").group is SigGroup.RELIC
