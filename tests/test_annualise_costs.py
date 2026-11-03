"""Shipped investment costs are annualised, and tools/annualise_costs.py does it once.

The eight island datasets (and their captive/ copies) held overnight capex in
`Inv_Cost_per_MWyr` / `Inv_Cost_per_MWhyr`, columns the model charges as annual
costs, so new build cost about 10x too much. Their batteries also had no power
cost at all. The first test pins every shipped dataset as annualised. The others
check the tool's arithmetic, its refusal to run twice and that it preserves
untouched fields byte for byte.
Solver-free; runs in CI.
"""
import csv
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tools import annualise_costs as ac
from tools.ntt.costs import crf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_no_shipped_dataset_holds_overnight_capex():
    tables = [p for p in glob.glob(os.path.join(ROOT, "data_indonesia", "**", "*generators.csv"),
                                   recursive=True)
              if "__" not in p and "variability" not in p]
    assert len(tables) > 50
    for p in tables:
        for r in _rows(p):
            if r["New_Build"].strip() != "1":
                continue
            tech = ac.tech_of([r["technology"], r["STOR"]], {"technology": 0, "STOR": 1})
            where = f"{os.path.relpath(p, ROOT)} R_ID {r['R_ID']} ({tech})"
            if tech == "solar":   # lowest overnight value shipped was 560,000; highest annualised 236,861
                assert float(r["Inv_Cost_per_MWyr"]) < 500_000, where
            if tech == "battery":
                assert float(r["Inv_Cost_per_MWyr"]) > 0, f"{where}: free battery power"


HEADER = "R_ID,Zone,Resource,technology,STOR,New_Build,Existing_Cap_MW,Inv_Cost_per_MWyr,Inv_Cost_per_MWhyr,Fixed_OM_Cost_per_MWyr"


def _dataset(tmp_path):
    folder = tmp_path / "island"
    folder.mkdir()
    (folder / "generators.csv").write_text(
        "﻿" + HEADER + "\r\n"
        "1,1,pltu_x,coal,0,-1,100,1600000,0,40000\r\n"
        "2,1,solar_new,solar,0,1,0,560000,0,9000\r\n"
        "3,1,bess_new,battery,1,1,0,0,578000,0\r\n"
        "4,1,ccgt_old,ccgt,0,0,50,660000,0,12000\r\n",
        encoding="utf-8", newline="")
    (folder / "ip_generators.csv").write_text(
        "R_ID,Zone,Industrial_Park,Resource,technology,STOR,New_Build,Existing_Cap_MW,Inv_Cost_per_MWyr,Inv_Cost_per_MWhyr,Fixed_OM_Cost_per_MWyr\n"
        "1,1,1,park_coal,coal_captive,0,-1,300,1500000,0,40000\n"
        "2,2,1,park_battery,,1,1,0,0,578000,0\n",
        encoding="utf-8", newline="")
    return folder


def test_annualise_arithmetic_and_preservation(tmp_path):
    folder = _dataset(tmp_path)
    log = ac.annualise(str(folder))
    raw = (folder / "generators.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw          # BOM + CRLF kept
    g = {r["R_ID"]: r for r in _rows(folder / "generators.csv")}
    assert float(g["1"]["Inv_Cost_per_MWyr"]) == pytest.approx(1_600_000 * crf(0.10, 30), abs=0.01)
    assert float(g["2"]["Inv_Cost_per_MWyr"]) == pytest.approx(560_000 * crf(0.10, 25), abs=0.01)
    assert float(g["3"]["Inv_Cost_per_MWyr"]) == pytest.approx(150_000 * crf(0.10, 15), abs=0.01)
    assert float(g["3"]["Inv_Cost_per_MWhyr"]) == pytest.approx(578_000 * crf(0.10, 15), abs=0.01)
    assert g["2"]["Fixed_OM_Cost_per_MWyr"] == "9000"                    # fixed O&M untouched
    ip = {r["R_ID"]: r for r in _rows(folder / "ip_generators.csv")}
    assert ip["1"]["Inv_Cost_per_MWyr"] == "1500000"                     # unlisted, existing only
    assert float(ip["2"]["Inv_Cost_per_MWyr"]) > 0                       # blank tech + STOR=1 = battery
    assert len(log) == 5


def test_refuses_to_run_twice(tmp_path):
    folder = _dataset(tmp_path)
    ac.annualise(str(folder))
    before = (folder / "generators.csv").read_bytes()
    with pytest.raises(SystemExit, match="already annualised"):
        ac.annualise(str(folder))
    assert (folder / "generators.csv").read_bytes() == before


def test_unlisted_new_build_technology_stops(tmp_path):
    folder = _dataset(tmp_path)
    with open(folder / "generators.csv", "a", encoding="utf-8", newline="") as fh:
        fh.write("5,1,tidal_new,tidal,0,1,0,9000000,0,0\r\n")
    before = (folder / "ip_generators.csv").read_bytes()
    with pytest.raises(SystemExit, match="no lifetime"):
        ac.annualise(str(folder))
    assert (folder / "ip_generators.csv").read_bytes() == before        # nothing written
