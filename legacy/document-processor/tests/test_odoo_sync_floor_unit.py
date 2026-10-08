"""Regression test: same-floor units with different unit letters (e.g. 29/F 29A vs
29B) must not collide into one x_c21_floor_unit value. See CLAUDE.md 2026-09-13
session summary — a pitching deck with 14 available_units synced only 13 Odoo
records because the dedup key used `floor or unit` instead of joining both."""

from src.nodes.odoo_sync import _map_fields, _sync_pitching_deck_units
from src.state import DocumentState, ExtractedData


def _state_with_units(units: list[dict]) -> DocumentState:
    return DocumentState(
        file_name="test.pdf",
        extracted=ExtractedData(raw={"building_name": "Test Building", "available_units": units}),
    )


def test_map_fields_joins_floor_and_unit():
    state = _state_with_units([{"floor": "29/F", "unit": "29A", "rent_monthly": 29596, "size_sqft": 1057}])
    unit = state.extracted.raw["available_units"][0]

    vals_a = _map_fields(state, doc_url=None, building_id=None, unit=unit)
    vals_b = _map_fields(
        state, doc_url=None, building_id=None,
        unit={"floor": "29/F", "unit": "29B", "rent_monthly": 29596, "size_sqft": 1057},
    )

    assert vals_a["x_c21_floor_unit"] == "29/F 29A"
    assert vals_b["x_c21_floor_unit"] == "29/F 29B"
    assert vals_a["x_c21_floor_unit"] != vals_b["x_c21_floor_unit"]


def test_sync_pitching_deck_units_creates_separate_records_for_same_floor(monkeypatch):
    units = [
        {"floor": "29/F", "unit": "29A", "rent_monthly": 29596, "size_sqft": 1057},
        {"floor": "29/F", "unit": "29B", "rent_monthly": 29596, "size_sqft": 1057},
    ]
    state = _state_with_units(units)

    # No existing records — every unit should be a fresh create.
    monkeypatch.setattr("src.nodes.odoo_sync._find_unit_record", lambda *a, **k: None)
    monkeypatch.setattr("src.nodes.odoo_sync._extract_unmapped", lambda raw: {})
    monkeypatch.setattr("src.nodes.odoo_sync._sync_extra_fields", lambda *a, **k: None)

    created_vals = []

    class FakeModels:
        def execute_kw(self, db, uid, api_key, model, method, args, kwargs=None):
            assert method == "create"
            created_vals.append(args[0])
            return len(created_vals)

    ids = _sync_pitching_deck_units(FakeModels(), 1, "key", state, None, None, units)

    assert len(ids) == 2, "29A and 29B must both be created, not collapsed into one record"
    floor_units = {v["x_c21_floor_unit"] for v in created_vals}
    assert floor_units == {"29/F 29A", "29/F 29B"}
