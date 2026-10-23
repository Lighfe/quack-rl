# Moved from tests/test_spellbook.py (#170), original text

def test_old_rulesets_have_no_spellbook():
    for version in ("v1", "v1.1", "v1.8"):
        rs = load_ruleset(version)
        assert rs.spellbook is None
        assert all(rs.component_name(c) == c.component for c in rs.chips)

