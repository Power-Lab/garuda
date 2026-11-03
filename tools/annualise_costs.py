#!/usr/bin/env python3
"""Annualise the overnight investment costs in an island dataset's generator tables.

`Inv_Cost_per_MWyr` and `Inv_Cost_per_MWhyr` are documented and charged as
annualised costs ($/MW-yr, $/MWh-yr), and optimizer.jl adds them unchanged to a
one-year objective. The eight inherited island datasets (and their captive/
copies) held **overnight** capex in those columns instead: solar 560,000 $/MW
is an installed cost (IRENA $691/kW), and read as annual it implies an LCOE of
about $394/MWh. New build therefore cost about ten times too much and was
never chosen. Batteries had no power cost at all (`Inv_Cost_per_MWyr = 0`).

This multiplies both columns by the capital recovery factor
CRF = r(1+r)^n / ((1+r)^n - 1) at r = 10 % WACC, with the technology's lifetime
n from `LIFETIME` below. Batteries get a power cost of 150,000 $/MW overnight,
annualised over 15 years. Their existing 578,000 $/MWh energy cost is annualised
over 15 years too. Fixed O&M is already annual and is not touched, and nor is
network.csv: `Line_Reinforcement_Cost_per_MWyr` is a flat 35,178 $/MW, which is
already annual in size. The method, lifetimes and battery power cost match
captive-indonesia-2025 (scripts/annualize_costs.py, commits 3bbb593 and
ed459f5), so the two models price the same candidates identically.

Every row of a listed technology is annualised in `generators.csv` and in the
site table (`site_`/`village_`/`ip_generators.csv`). Only `New_Build = 1` rows
enter the objective. A technology not listed is left alone when it has no
`New_Build = 1` row (existing `coal_captive` units). A new-build row of an
unlisted technology stops the run, because its lifetime is a decision, not a
guess. A row with a blank technology and `STOR = 1` (the park batteries of
kalimantan and north_maluku, named `*_battery`) is treated as a battery.

The tool refuses to run twice. If a new-build solar row is already below
200,000 $/MW-yr, or a battery already has a power cost, it stops before writing
anything. Each changed row is otherwise rewritten in place: the line is re-emitted
through the csv module, with BOM, line endings and every other field preserved,
and checked to round-trip first. The changed rows are appended to
data_indonesia/corrections/annualised_costs.csv, and each folder must pass
`tools/validate_schema.validate_dataset` afterwards or the run stops.

Usage (from the repository root):
    python3 tools/annualise_costs.py data_indonesia/2035/sulawesi [more folders ...]
    python3 tools/annualise_costs.py --all     # every shipped island dataset still at overnight cost
"""
import argparse
import csv
import glob
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.ntt.costs import crf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WACC = 0.10
LIFETIME = {'solar': 25, 'wind': 25, 'geothermal': 30, 'battery': 15, 'gas': 30, 'ccgt': 30,
            'hydropower': 50, 'hydropower_mini': 50, 'biomass': 25, 'biogas': 25, 'trash': 25,
            'diesel': 20, 'coal': 30, 'pumped_storage': 50}
BATTERY_POWER_OVERNIGHT = 150_000.0   # $/MW
GUARD = 200_000.0                      # new-build solar above this is still overnight capex
SITE_PREFIXES = ('site', 'village', 'ip')
LOG = os.path.join(ROOT, 'data_indonesia', 'corrections', 'annualised_costs.csv')
LOG_FIELDS = ['dataset', 'file', 'R_ID', 'Resource', 'technology', 'New_Build', 'lifetime_yr',
              'crf', 'Inv_Cost_per_MWyr_old', 'Inv_Cost_per_MWyr_new',
              'Inv_Cost_per_MWhyr_old', 'Inv_Cost_per_MWhyr_new']


def fmt(x):
    return f'{x:.2f}'.rstrip('0').rstrip('.')


def tech_of(r, c):
    tech = r[c['technology']]
    return 'battery' if tech == '' and r[c['STOR']].strip() == '1' else tech


def parse(line):
    return next(csv.reader([line]))


def unparse(fields):
    out = io.StringIO()
    csv.writer(out, lineterminator='').writerow(fields)
    return out.getvalue()


def tables(folder):
    """generators.csv plus the site table that site_aliases.jl would load, if any."""
    out = [os.path.join(folder, 'generators.csv')]
    for p in SITE_PREFIXES:
        f = os.path.join(folder, f'{p}_generators.csv')
        if os.path.exists(f):
            out.append(f)
            break
    return out


def load(path):
    """Read and check one table; raise SystemExit on anything this tool must not touch."""
    raw = open(path, 'rb').read()
    text = raw.decode('utf-8-sig')
    eol = '\r\n' if '\r\n' in text else '\n'
    lines = text.split(eol)
    head = parse(lines[0])
    c = {k: head.index(k) for k in ('R_ID', 'Resource', 'technology', 'New_Build',
                                   'Inv_Cost_per_MWyr', 'Inv_Cost_per_MWhyr', 'STOR')}
    rows = {i: parse(line) for i, line in enumerate(lines[1:], start=1) if line}
    where = os.path.relpath(path, ROOT)
    for i, r in rows.items():
        if unparse(r) != lines[i]:
            raise SystemExit(f'{where}:{i + 1} does not round-trip through csv')
        tech, new = tech_of(r, c), r[c['New_Build']].strip() == '1'
        rid = r[c['R_ID']]
        if tech == 'solar' and new and float(r[c['Inv_Cost_per_MWyr']]) < GUARD:
            raise SystemExit(f'{where} R_ID {rid}: new-build solar costs '
                             f'{r[c["Inv_Cost_per_MWyr"]]} $/MW-yr, below {GUARD:,.0f}: '
                             'already annualised')
        if tech not in LIFETIME and new:
            raise SystemExit(f'{where} R_ID {rid}: new-build technology {tech!r} has no '
                             'lifetime; add it to LIFETIME by decision, not by guess')
        if tech != 'battery' and float(r[c['Inv_Cost_per_MWhyr']] or 0) != 0:
            raise SystemExit(f'{where} R_ID {rid}: {tech} has an energy cost')
        if tech == 'battery' and float(r[c['Inv_Cost_per_MWyr']] or 0) != 0:
            raise SystemExit(f'{where} R_ID {rid}: battery already has a power cost')
    return raw.startswith(b'\xef\xbb\xbf'), eol, lines, c, rows


def annualise(folder):
    """Annualise one dataset folder in place; return its log rows."""
    loaded = {path: load(path) for path in tables(folder)}   # check every table before writing any
    dataset = os.path.relpath(folder, os.path.join(ROOT, 'data_indonesia'))
    log = []
    for path, (bom, eol, lines, c, rows) in loaded.items():
        changed = 0
        for i, r in rows.items():
            tech = tech_of(r, c)
            if tech not in LIFETIME:
                continue
            n = LIFETIME[tech]
            f = crf(WACC, n)
            old_mw, old_mwh = r[c['Inv_Cost_per_MWyr']], r[c['Inv_Cost_per_MWhyr']]
            overnight_mw = BATTERY_POWER_OVERNIGHT if tech == 'battery' else float(old_mw)
            r[c['Inv_Cost_per_MWyr']] = fmt(overnight_mw * f)
            if float(old_mwh or 0) != 0:
                r[c['Inv_Cost_per_MWhyr']] = fmt(float(old_mwh) * f)
            log.append({'dataset': dataset, 'file': os.path.basename(path),
                        'R_ID': r[c['R_ID']], 'Resource': r[c['Resource']], 'technology': tech,
                        'New_Build': r[c['New_Build']], 'lifetime_yr': n, 'crf': f'{f:.6f}',
                        'Inv_Cost_per_MWyr_old': old_mw,
                        'Inv_Cost_per_MWyr_new': r[c['Inv_Cost_per_MWyr']],
                        'Inv_Cost_per_MWhyr_old': old_mwh,
                        'Inv_Cost_per_MWhyr_new': r[c['Inv_Cost_per_MWhyr']]})
            lines[i] = unparse(r)
            changed += 1
        with open(path, 'wb') as fh:
            fh.write((b'\xef\xbb\xbf' if bom else b'') + eol.join(lines).encode('utf-8'))
        left = sorted({tech_of(r, c) for r in rows.values() if tech_of(r, c) not in LIFETIME})
        print(f'{dataset}/{os.path.basename(path)}: {changed} rows annualised'
              + (f'; left as is (existing units only): {", ".join(left)}' if left else ''))
    return log


def overnight_datasets():
    """Shipped (non-derived) dataset folders whose new-build solar is still at overnight cost."""
    out = []
    for g in sorted(glob.glob(os.path.join(ROOT, 'data_indonesia', '**', 'generators.csv'),
                              recursive=True)):
        folder = os.path.dirname(g)
        if '__' in os.path.basename(folder):
            continue
        with open(g, encoding='utf-8-sig', newline='') as fh:
            solar = [float(r['Inv_Cost_per_MWyr']) for r in csv.DictReader(fh)
                     if r['technology'] == 'solar' and r['New_Build'].strip() == '1']
        # same test as the guard in load(): overnight only if no new solar is below GUARD
        # (a few rows carry 2,150,000 overnight, which annualises to 236,861)
        if solar and min(solar) >= GUARD:
            out.append(folder)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folders', nargs='*', help='dataset folders, e.g. data_indonesia/2035/sulawesi')
    ap.add_argument('--all', action='store_true',
                    help='every shipped dataset whose new-build solar is still at overnight cost')
    args = ap.parse_args()
    folders = overnight_datasets() if args.all else [os.path.abspath(f) for f in args.folders]
    if not folders:
        ap.error('no dataset folders given (or none left at overnight cost with --all)')

    from tools.validate_schema import validate_dataset
    log = []
    for folder in folders:
        log += annualise(folder)
        errors = validate_dataset(folder)[0]
        if errors:
            raise SystemExit(f'{folder}: schema validation failed after annualising:\n  '
                             + '\n  '.join(errors))

    new_log = not os.path.exists(LOG)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        if new_log:
            w.writeheader()
        w.writerows(log)
    print(f'{len(folders)} datasets; logged {len(log)} rows to {os.path.relpath(LOG, ROOT)}')
    for tech, n in sorted(LIFETIME.items(), key=lambda x: (x[1], x[0])):
        print(f'  {tech:16s} {n:3d} yr  CRF {crf(WACC, n):.6f}')


if __name__ == '__main__':
    main()
