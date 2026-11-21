"""Settings and easy mode (uses a temporary vaults root)."""

import pytest

from ringwraith import campaign as cp


def test_easy_mode_switches_tn_and_strider(tmp_path):
    (tmp_path / "test-camp").mkdir()
    cp.set_active("test-camp", tmp_path)
    s = cp.load_settings(root=tmp_path)
    assert s["difficulty"]["easy"] is False
    assert cp.hero_tn(5, s) == 15 and not cp.has_strider_feature(s)
    s = cp.set_value("difficulty.easy", True, root=tmp_path)
    assert cp.hero_tn(5, s) == 13 and cp.has_strider_feature(s)
    assert cp.load_settings(root=tmp_path)["dice"]["mode"] == "auto"   # defaults survive merge



def test_a_strider_campaign_plays_by_the_strider_rules(tmp_path):
    (tmp_path / "lone").mkdir()
    cp.set_active("lone", tmp_path)
    s = cp.set_value("campaign.mode", "strider", root=tmp_path)
    assert cp.hero_tn(5, s) == 13 and cp.has_strider_feature(s)          # 18 - Attribute and the feature, easy or not

def test_no_active_campaign(tmp_path):
    with pytest.raises(cp.CampaignError):
        cp.load_settings(root=tmp_path)
