from templates.library import TEMPLATES


def test_minimum_twenty_templates() -> None:
    assert len(TEMPLATES) >= 20
    assert len({template.id for template in TEMPLATES}) == len(TEMPLATES)
