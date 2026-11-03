"""Zone and site ids in every shipped dataset meet what the loader's indexing assumes.

input_data.jl reads ``demand[t,z]`` and ``village_demand[t,vil]`` by column
position, so the zones and site ids must be exactly 1..N. The loader sorts both
and now refuses gaps. Before the sort, jawa_bali's first-appearance zone order
1,2,3,4,6,7,5 gave zones 5, 6 and 7 one another's load, and schema validation
passed it. These checks run on the CSVs, so a new dataset that breaks the
invariant fails here before it reaches the model.

A site's grid bus (``village_zone``) is the Zone of its first listed generator.
Some industrial-park battery rows carry a different Zone from the park's coal
units (kalimantan, sumatera), so the rule only holds while the coal_captive
units are in one zone and listed first. The captive-indonesia-2025 model mixed
generator R_IDs with park numbers at this point and drew some park imports from
the wrong zone. The last test pins the coal-zone condition.
Solver-free; runs in CI.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASETS = sorted(
    os.path.dirname(p)
    for p in glob.glob(os.path.join(ROOT, "data_indonesia", "**", "generators.csv"), recursive=True)
    if "__" not in os.path.basename(os.path.dirname(p))   # derived datasets are gitignored
)
SITE_PREFIXES = ("site", "village", "ip")
SITE_ID_COLUMNS = ("Site", "Village", "Industrial_Park")


def _read(path):
    return pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])


def _site_generators(folder):
    """(table, id column) for the first site prefix present, as site_aliases.jl resolves it."""
    for p in SITE_PREFIXES:
        f = os.path.join(folder, f"{p}_generators.csv")
        if os.path.exists(f):
            g = _read(f)
            return g, next(c for c in SITE_ID_COLUMNS if c in g.columns)
    return None, None


def _id(folder):
    return os.path.relpath(folder, os.path.join(ROOT, "data_indonesia"))


def test_datasets_found():
    assert len(DATASETS) >= 30


@pytest.mark.parametrize("folder", DATASETS, ids=_id)
def test_zones_are_1_to_n_with_demand_columns(folder):
    zones = sorted(int(z) for z in _read(os.path.join(folder, "generators.csv"))["Zone"].dropna().unique())
    assert zones == list(range(1, len(zones) + 1)), zones
    demand_cols = set(_read(os.path.join(folder, "demand.csv")).columns)
    assert {f"demand_z{z}" for z in zones} <= demand_cols


@pytest.mark.parametrize("folder", DATASETS, ids=_id)
def test_site_ids_are_1_to_n(folder):
    g, idc = _site_generators(folder)
    if g is None:
        pytest.skip("no site layer")
    ids = sorted(int(v) for v in g[idc].dropna().unique())
    assert ids == list(range(1, len(ids) + 1)), f"{len(ids)} sites, ids {ids[:5]}..{ids[-5:]}"


@pytest.mark.parametrize("folder", DATASETS, ids=_id)
def test_site_bus_is_the_coal_captive_zone(folder):
    g, idc = _site_generators(folder)
    if g is None:
        pytest.skip("no site layer")
    zones = set(int(z) for z in _read(os.path.join(folder, "generators.csv"))["Zone"].dropna())
    first = g.groupby(idc, sort=False)["Zone"].first()          # village_zone in input_data.jl
    assert set(int(z) for z in first) <= zones
    coal = g[g["technology"] == "coal_captive"].groupby(idc)["Zone"].unique()
    for site, zs in coal.items():
        assert len(zs) == 1, f"site {site}: coal_captive units in zones {sorted(zs)}"
        assert int(zs[0]) == int(first[site]), (
            f"site {site}: grid bus is zone {first[site]} (first listed generator) "
            f"but its coal_captive units are in zone {zs[0]}")
