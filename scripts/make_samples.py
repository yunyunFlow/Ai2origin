#!/usr/bin/env python3
"""Create public, explicitly synthetic fixtures; never read project data."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def write_csv(path, headers, rows):
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def make_samples(target):
    if target.exists() or target.is_symlink():
        raise FileExistsError("Use a new sample directory")
    target.mkdir(parents=True)
    x = np.linspace(0, 8, 41)
    a = np.exp(-x / 4) * np.sin(x) + 0.5
    b = np.exp(-x / 5) * np.cos(x + 0.3) + 0.4
    write_csv(target / "xy.csv", ["x", "a", "a_lower", "a_upper", "b", "b_lower", "b_upper"],
              [[format(float(v), ".17g") for v in row] for row in zip(x, a, a-0.12, a+0.12, b, b-0.10, b+0.10)])
    xs, ys = np.linspace(-2, 2, 13), np.linspace(-1.5, 1.5, 9)
    rows = []
    for y in ys:
        for xval in xs:
            z = 0.85 * np.exp(-((xval-0.65)**2 + (y-0.35)**2) / 0.6) - 0.75 * np.exp(-((xval+0.8)**2 + (y+0.45)**2) / 0.45)
            rows.append([format(float(v), ".17g") for v in (xval, y, z)])
    write_csv(target / "heatmap.csv", ["x", "y", "z"], rows)
    rows = []
    # Entirely invented diffraction-like scans. No signal/PSD/project input.
    for scan in range(1, 10):
        for angle in np.linspace(10, 80, 141):
            signal = 0.02 + 0.9*np.exp(-((angle-24-0.15*scan)/0.9)**2) + 0.6*np.exp(-((angle-47+0.1*scan)/1.1)**2) + 0.4*np.exp(-((angle-65)/1.2)**2)
            rows.append([format(float(v), ".17g") for v in (angle, scan, signal)])
    write_csv(target / "xrd.csv", ["toy_angle", "toy_scan", "toy_intensity"], rows)
    rng = np.random.default_rng(1729)
    rows = []
    for group, count, mean, sd, outlier in [
            ("Group A", 24, -0.65, 0.36, 1.60),
            ("Group B", 32, 0.10, 0.62, -2.40),
            ("Group C", 20, 1.10, 0.30, 2.50)]:
        values = rng.normal(mean, sd, count)
        values[-1] = outlier
        for i, value in enumerate(values, 1):
            rows.append([group.replace(" ", "") + "-" + str(i), group, format(float(value), ".17g")])
    write_csv(target / "raincloud.csv", ["sample_id", "group", "value"], rows)
    config = {
        "schema_version": 1,
        "style": {"series_overrides": {g: {"marker_size_pt": 2.0} for g in ("Group A", "Group B", "Group C")}},
        "plots": [
            {"id": "xy", "kind": "line", "csv": "xy.csv", "x": "x", "synthetic": True,
             "title": "Synthetic curves",
             "labels": {"x": "Coordinate (a.u.)", "y": "Response (a.u.)"},
             "series": [
                 {"column": "a", "label": "A", "lower": "a_lower", "upper": "a_upper",
                  "uncertainty_definition": "Assigned synthetic ±0.12 display band; not a CI"},
                 {"column": "b", "label": "B", "lower": "b_lower", "upper": "b_upper",
                  "uncertainty_definition": "Assigned synthetic ±0.10 display band; not a CI"}]},
            {"id": "heatmap", "kind": "heatmap", "csv": "heatmap.csv", "x": "x", "y": "y", "z": "z",
             "synthetic": True, "title": "Synthetic signed field", "color_range": [-1, 1], "center": 0,
             "cmap": ["#2166AC", "#F7F7F7", "#B2182B"], "labels": {"x": "Toy x (a.u.)", "y": "Toy y (a.u.)", "color": "Toy field (a.u.)"}},
            {"id": "raincloud", "kind": "raincloud", "csv": "raincloud.csv", "group": "group", "value": "value",
             "order": ["Group A", "Group B", "Group C"], "synthetic": True,
             "title": "Synthetic raincloud",
             "bandwidth": 0.20, "seed": 1729, "labels": {"x": "Observable (a.u.)", "y": "Group"}},
            {"id": "smooth", "kind": "heatmap", "csv": "xrd.csv", "x": "toy_angle", "y": "toy_scan", "z": "toy_intensity",
             "synthetic": True, "title": "Synthetic XRD scans", "color_range": [0, 1], "center": 0.5,
             "caption": "Invented diffraction-like peaks on invented axes. 9x141 raw nodes retained; display-only bilinear factor 8 gives 65x1121 nodes, 256 levels, no new observations or higher scientific resolution. White=0.5, not zero. No measured diffraction or phase claim.",
             "color_levels": 256, "interpolation": {"method": "bilinear", "factor": 8},
             "cmap": ["#2166AC", "#F7F7F7", "#B2182B"],
             "labels": {"x": "2θ (°)", "y": "Scan index (synthetic)", "color": "Intensity (a.u.)"}},
            {"id": "violin", "kind": "raincloud", "csv": "raincloud.csv", "group": "group", "value": "value",
             "order": ["Group A", "Group B", "Group C"], "synthetic": True, "title": "Full violin + rain",
             "bandwidth": 0.20, "seed": 1729, "cloud_shape": "full", "orientation": "vertical",
             "group_labels": {"Group A": "A", "Group B": "B", "Group C": "C"},
             "labels": {"x": "Group", "y": "Observable (a.u.)"}}
        ]}
    for plot in config['plots']:
        plot['title']=''
        if plot['kind']=='raincloud':
            plot.update(summary=False,cloud_support='observed',density_scale='width',cloud_fill=True)
            plot['bandwidth']='scott'
            plot['caption']='All 76 invented raw observations retained. Translucent cloud silhouette and points only; no mean/median/box/whisker displayed. Gaussian KDE with per-group Scott bandwidth h=sample SD*n^(-1/5), displayed over each raw min/max (cut=0), per-group equal maximum display width. Native vertical fill uses source-bound closed polygons with zero outline stroke, preventing implicit baseline drop lines. No taper, gap splitting, denoising or filtering. Density between observations is estimator output, not new samples. Jitter seed 1729; not statistical inference.'
    (target / "demo.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Color comparisons share identical invented values, never project input.
    rows=[]
    for y in np.linspace(-1.5,1.5,9):
        for xv in np.linspace(-2,2,13):
            value=(np.sin(1.5*(xv+1))+np.cos(2*y)+2)/4
            rows.append([format(float(v),'.17g') for v in (xv,y,value)])
    write_csv(target/'colors-map.csv',['x','y','z'],rows)
    x=np.linspace(0,5,41)
    write_csv(target/'colors-lines.csv',['x']+['v'+str(i) for i in range(1,8)],
              [[format(float(v),'.17g') for v in row] for row in zip(x,*[i+.3*np.sin(x+i*.4) for i in range(7)])])
    colors={'schema_version':1,'plots':[{'id':'palette-lines','kind':'line','csv':'colors-lines.csv','x':'x',
        'synthetic':True,'title':'','x_range':[0,10],'y_range':[-.5,7.5],
        'labels':{'x':'Toy x (a.u.)','y':'Toy response (a.u.)'},
        'series':[{'column':'v'+str(i),'label':name} for i,name in enumerate(['Red','Blue','Green','Purple','Orange','Gray','Pink'],1)],
        'caption':'Seven entirely invented curves; default red/blue/green/purple/orange/gray/pink identities. No measured observable or scientific inference.'}]}
    for name,cmap,label in (('redwhiteblue','redwhiteblue','Blue–white–red'),
                           ('reimu26','purplegreen','Purple–green–yellow'),
                           ('reimu27','violetgold','Violet–orange–yellow'),
                           ('rainbow','rainbow','Rainbow'),
                           ('rainbow_r','rainbow_r','Reversed rainbow')):
        meaning='white=0.5, not zero' if name=='redwhiteblue' else 'no white/zero threshold is implied'
        colors['plots'].append({'id':'palette-'+name,'kind':'heatmap','csv':'colors-map.csv','x':'x','y':'y','z':'z',
            'synthetic':True,'title':'','cmap':cmap,'color_range':[0,1],'color_levels':256,
            'interpolation':{'method':'bilinear','factor':4},
            'labels':{'x':'Toy x (a.u.)','y':'Toy y (a.u.)','color':'Toy field (a.u.)'},
            'caption':'Identical invented 9x13 grid for palette comparison; '+label+'; '+meaning+'. Display-only factor-4 bilinear interpolation, 256 color bins; exact raw grid retained. No new observations or higher scientific resolution.'})
    (target/'colors.json').write_text(json.dumps(colors,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cycles=np.arange(1,121);toy_rng=np.random.default_rng(20261004)
    capacities=[start*(1-decay*cycles)+1.2*np.sin(cycles/8+phase)+toy_rng.normal(0,.45,len(cycles))
                for start,decay,phase in [(160,.0014,0),(148,.002,1),(155,.0006,2)]]
    write_csv(target/'walkthrough.csv',['cycle','capacity_a','capacity_b','capacity_c'],
              [[format(float(v),'.17g') for v in row] for row in zip(cycles,*capacities)])
    walkthrough={'schema_version':1,'style':{'marker':{'size_pt':2.5}},'plots':[
        {'id':'walkthrough','kind':'line_symbol','csv':'walkthrough.csv','x':'cycle','synthetic':True,'title':'',
         'x_range':[0,125],'y_range':[80,180],'x_tick_step':25,'y_tick_step':20,
         'labels':{'x':'Cycle number','y':'Specific capacity (mAh g^-1)'},
         'series':[{'column':'capacity_'+letter,'label':'Demo '+letter.upper()} for letter in 'abc'],
         'caption':'Entirely invented 120-cycle capacity series A/B/C (360 raw plotted points). Seed 20261004; capacity=start*(1-decay*cycle)+1.2*sin(cycle/8+phase)+Gaussian noise (mean=0, SD=0.45 mAh g^-1), with (start,decay,phase)=(160,0.0014,0)/(148,0.002,1)/(155,0.0006,2). Assigned mass-specific capacity unit mAh g^-1; no active-mass, cell, current, voltage or measured cycling evidence. Raw acquisition order and every value retained; straight connections only, no smoothing, filtering, normalization, interpolation, fit or statistical inference.'}]}
    (target/'walkthrough.json').write_text(json.dumps(walkthrough,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    make_samples(parser.parse_args().out)
