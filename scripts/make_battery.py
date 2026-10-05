#!/usr/bin/env python3
"""Invented battery charge/discharge fixtures; no measured data or fitted model."""
import csv
import math
from pathlib import Path

def time_rows():
    rows = []
    for t in range(0, 1001, 10):
        charge = t <= 500
        elapsed = t if charge else t - 500
        voltage = .9 + .9 * t / 500 if charge else 1.7 - .8 * elapsed / 500
        rows.append(['Demo', '001', '1', '1' if charge else '2',
                     'charge' if charge else 'discharge', str(t), format(voltage, '.8g'),
                     '0.72' if charge else '-0.72', format(.72 * elapsed / 3600, '.8g')])
    return rows

def capacity_rows(rate=False):
    """Assign independent mass-specific branch grids, not resampled records."""
    groups = [('r02',240,0),('r05',205,.025),('r1',170,.05),('r2',135,.075)] if rate else [('c1',220,0),('c50',205,.025),('c100',190,.05)]
    rows=[]
    for i in range(101):
        u=i/100; row=[]
        for _,qmax,polarization in groups:
            charge=1.52+polarization+.08*u+.30*u**8-.28*math.exp(-u/.03)
            discharge=1.38-polarization-.08*u-.30*u**8+.28*math.exp(-u/.03)
            row.extend(format(v,'.10g') for v in (qmax*u,charge,.96*qmax*u,discharge))
        rows.append(row)
    return rows

def capacity_headers(rate=False):
    groups=['r02','r05','r1','r2'] if rate else ['c1','c50','c100']
    return [group+'_'+field for group in groups for field in ('charge_mAh_g','charge_V','discharge_mAh_g','discharge_V')]

def main():
    target = Path(__file__).resolve().parents[1] / 'templates'
    for name, headers, rows in [
        ('battery-time.csv', ['sample','channel','cycle','step','branch','time_s','voltage_V','current_mA','branch_capacity_mAh'], time_rows()),
        ('battery-capacity.csv', capacity_headers(), capacity_rows()),
        ('battery-rate.csv', capacity_headers(True), capacity_rows(True))]:
        with (target/name).open('w', newline='', encoding='utf-8') as f:
            w=csv.writer(f,lineterminator='\n');w.writerow(headers);w.writerows(rows)

if __name__ == '__main__': main()
