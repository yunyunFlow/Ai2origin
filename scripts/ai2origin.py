#!/usr/bin/env python3
"""Prepare reproducible plot geometry; optionally render a Python preview."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
from decimal import Decimal
import re
import importlib.util
import sys
from pathlib import Path

import numpy as np

_style_spec = importlib.util.spec_from_file_location("ai2origin_style", Path(__file__).with_name("style.py"))
STYLE = importlib.util.module_from_spec(_style_spec)
_style_spec.loader.exec_module(STYLE)
COLORMAP_PATH=Path(__file__).resolve().parents[1]/'assets/colormaps.json'
_SYSTEM_FONTS_LOADED = False


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def load_json(path):
    def bad_constant(value):
        raise ValueError("Non-finite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_object, parse_constant=bad_constant)


def plain_text(value):
    """Scientific display text; literal percent is not an executable token."""
    value = str(value).replace('\u2212','-')
    if any(ch in value for ch in ('"', ";", "$", "\\")) or any(ord(ch)<32 for ch in value):
        raise ValueError("Use plain text labels without control characters or commands")
    return value


def lt_string(value):
    """Quote native text, preserving the LabTalk substitution restriction."""
    value = plain_text(value)
    if "%" in value:
        raise ValueError("Use plain text labels without LabTalk control characters")
    return '"' + value + '"'


def num(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Non-finite coordinate")
    return format(value, ".17g")


def numeric(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be a finite JSON number")
    return float(value)


def math_text(value):
    # ASCII prime tokens in impedance labels can trigger reserved-label quoting
    # in Origin2021. Use the equivalent real mathematical prime glyphs.
    return re.sub(r"\bZ('{1,2})(?!')",lambda m:'Z'+('′' if len(m[1])==1 else '″'),value)


def display_label(value, native=False):
    """Bounded unit exponents use Arial digits with native/mathtext superscripts."""
    value=math_text(value)
    plain=lt_string(value)[1:-1] if native else plain_text(value)
    pattern=r'\b(cm|g|s|Å|nm|m|kg|V|A|C|K|mol|Hz|mAh)\^(-?\d{1,2}(?:\.\d{1,2})?)\b'
    text=re.sub(pattern,lambda m:m[1]+'\\+('+m[2]+')' if native else r'$\mathrm{'+m[1]+'}^{'+m[2]+'}$',plain)
    text=text.replace('μ0H',r'μ\-(0)H' if native else r'$\mu_0 H$')
    for symbol in ('I_a','I_c','I_p'):
        text=text.replace(symbol,symbol[0]+'\\-('+symbol[2]+')' if native else r'$\mathrm{'+symbol[0]+'}_{'+symbol[2]+'}$')
    return '"'+text+'"' if native else text


def color_map(spec):
    from matplotlib import colormaps
    from matplotlib.colors import ListedColormap,to_rgba
    catalog=load_json(COLORMAP_PATH)
    name=spec.get('cmap',catalog['default'])
    preset=catalog['maps'].get(name) if isinstance(name,str) else None
    levels=spec.get('color_levels',16)
    if type(levels) is not int or not 2<=levels<=256:raise ValueError('color_levels must be an integer 2..256')
    reversed_palette=bool(preset and 'reverse_of' in preset)
    if reversed_palette:preset=catalog['maps'][preset['reverse_of']]
    stops=preset.get('colors') if preset else name if isinstance(name,list) else None
    neutral=None
    if stops is not None:
        if len(stops) < 2:
            raise ValueError("A custom colormap requires at least two colors")
        for value in stops:
            STYLE.color(value, "cmap")
        rgba=np.array([to_rgba(c) for c in stops]);positions=np.linspace(0,1,len(stops))
        colors=np.array([np.interp(np.linspace(0,1,levels),positions,rgba[:,c]) for c in range(4)]).T
        neutral=np.array([np.interp(.5,positions,rgba[:,c]) for c in range(4)])
        if preset and 'neutral' in preset:neutral=np.array(to_rgba(preset['neutral']))
    else:
        cmap=colormaps[preset['matplotlib'] if preset else name]
        colors=cmap(np.linspace(0,1,levels));neutral=np.array(cmap(.5))
    if 'center' in spec or preset and 'neutral' in preset:
        if levels<3:raise ValueError('A declared midpoint requires at least three color levels')
        # An even palette has no unique middle bin. Both adjacent bins are
        # neutral so the declared center is exact in native and Python output.
        colors[(levels-1)//2:levels//2+1]=neutral
    if reversed_palette:colors=colors[::-1].copy()
    return ListedColormap(colors,name='ai2origin')


def colorbar_labels(limits):
    values=np.linspace(*limits,5)
    for precision in range(2,18):
        labels=[format(float(v),'.%dg'%precision) for v in values]
        if len(set(labels))==len(labels) and all(abs(float(label)-value)<=min(np.diff(values))*.01 for label,value in zip(labels,values)):
            return labels
    raise ValueError('Colorbar interval is not numerically resolvable')


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            headers = next(reader, [])
        except csv.Error as exc:
            raise ValueError('Malformed CSV header: '+str(exc)) from exc
        if not headers or len(set(headers)) != len(headers) or any(not h.strip() for h in headers):
            raise ValueError("CSV headers must be nonempty and unique")
        rows = []
        try:
            records = list(reader)
        except csv.Error as exc:
            raise ValueError('Malformed CSV: '+str(exc)) from exc
        for index, row in enumerate(records, 2):
            if len(row) != len(headers):
                raise ValueError("CSV width mismatch at row " + str(index))
            rows.append(dict(zip(headers, row)))
    if not rows:
        raise ValueError("CSV contains no observations")
    return rows


def column(rows, key):
    if not isinstance(key,str) or not key.strip():
        raise ValueError('Numeric column name must be a nonempty string')
    try:
        values = np.array([float(row[key]) for row in rows], dtype=float)
    except (KeyError, ValueError) as exc:
        raise ValueError("Missing or non-numeric column: " + key) from exc
    if not np.all(np.isfinite(values)):
        raise ValueError("Non-finite values in " + key + "; define a missing-data policy first")
    if any(value == 0 and Decimal(str(row[key])) != 0 for value, row in zip(values, rows)):
        raise ValueError('Underflowing numeric value in ' + key + '; not representable as a nonzero coordinate')
    return values


def heatmap_grid(rows, x_key, y_key, z_key):
    x, y, z = (column(rows, key) for key in (x_key, y_key, z_key))
    xs, ys = np.unique(x), np.unique(y)
    if len(xs) < 2 or len(ys) < 2:
        raise ValueError("Heatmap needs at least two distinct coordinates per axis")
    grid = np.full((len(ys), len(xs)), np.nan)
    for xi, yi, zi in zip(x, y, z):
        ix, iy = np.searchsorted(xs, xi), np.searchsorted(ys, yi)
        if math.isfinite(grid[iy, ix]):
            raise ValueError("Duplicate heatmap cell; choose an explicit aggregation before plotting")
        grid[iy, ix] = zi
    if not np.all(np.isfinite(grid)):
        raise ValueError("Incomplete grid; do not silently interpolate or replace missing cells with zero")
    return xs, ys, grid


def heatmap_display(rows, spec):
    """Display-only bilinear resampling; retain the unmodified source grid."""
    xs, ys, raw = heatmap_grid(rows, spec["x"], spec["y"], spec["z"])
    interpolation = spec.get("interpolation", {"method": "none"})
    if not isinstance(interpolation, dict) or set(interpolation) - {"method", "factor"}:
        raise ValueError("interpolation requires method and optional factor")
    if interpolation.get("method") == "none":
        if "factor" in interpolation:
            raise ValueError("factor requires bilinear interpolation")
        return xs, ys, raw, (xs, ys, raw), "none"
    factor = interpolation.get("factor")
    if interpolation.get("method") != "bilinear" or type(factor) is not int or not 2 <= factor <= 12:
        raise ValueError("Use explicit bilinear interpolation with integer factor 2..12")
    nx, ny = (len(xs)-1)*factor+1, (len(ys)-1)*factor+1
    if nx * ny > 100000:
        raise ValueError("Display grid exceeds 100000 cells; reduce interpolation factor")
    # Subdivide existing coordinate intervals; irregular physical spacing is
    # preserved. No extrapolation, overshoot, denoising or missing-cell filling.
    subdivide = lambda coordinates: np.concatenate([
        np.linspace(a, b, factor, endpoint=False) for a, b in zip(coordinates[:-1], coordinates[1:])
    ] + [coordinates[-1:]])
    if spec.get("x_scale") == "log10" and np.any(xs <= 0):
        raise ValueError("Log X requires positive coordinates")
    axis_x = np.log10(xs) if spec.get("x_scale") == "log10" else xs
    display_x, dy = subdivide(axis_x), subdivide(ys)
    dx = 10**display_x if spec.get("x_scale") == "log10" else display_x
    dx[::factor] = xs  # preserve exact source coordinates, including roundoff
    along_x = np.array([np.interp(display_x, axis_x, row) for row in raw])
    display = np.array([np.interp(dy, ys, col) for col in along_x.T]).T
    return dx, dy, display, (xs, ys, raw), "bilinear factor=" + str(factor) + (" in log10(x),y" if spec.get("x_scale") == "log10" else "")


def pchip_connection(x, y, factor=16):
    """Shape-preserving display interpolation, not extra NEB images or a fit."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or not np.all(np.diff(x) > 0):
        raise ValueError("PCHIP requires at least three strictly increasing nodes")
    if type(factor) is not int or not 2 <= factor <= 64:
        raise ValueError("PCHIP factor must be integer 2..64")
    h = np.diff(x); delta = np.diff(y) / h; slopes = np.zeros_like(y)
    for i in range(1, len(x)-1):
        if delta[i-1]*delta[i] > 0:
            w1, w2 = 2*h[i]+h[i-1], h[i]+2*h[i-1]
            slopes[i] = (w1+w2)/(w1/delta[i-1]+w2/delta[i])
    def endpoint(h0, h1, d0, d1):
        m=((2*h0+h1)*d0-h0*d1)/(h0+h1)
        if m*d0 <= 0: return 0.0
        return 3*d0 if d0*d1 < 0 and abs(m)>3*abs(d0) else m
    slopes[0]=endpoint(h[0],h[1],delta[0],delta[1])
    slopes[-1]=endpoint(h[-1],h[-2],delta[-1],delta[-2])
    xx=[]; yy=[]
    for i in range(len(h)):
        t=np.arange(factor)/factor
        xx.extend(x[i]+t*h[i])
        yy.extend((2*t**3-3*t**2+1)*y[i]+(t**3-2*t**2+t)*h[i]*slopes[i]+(-2*t**3+3*t**2)*y[i+1]+(t**3-t**2)*h[i]*slopes[i+1])
    return np.r_[xx,x[-1]], np.r_[yy,y[-1]]


def legend_corner(spec, rows):
    """Choose a corner by overlap with dense curve/band geometry in axis space."""
    all_x=[column(rows,s.get('x',spec['x'])) for s in spec['series']]
    if spec.get('x_scale')=='log10':
        if any(np.any(x<=0) for x in all_x):
            raise ValueError('Log X requires positive data in every series')
        all_x=[np.log10(x) for x in all_x]
    xr=spec.get('x_range',[float(min(x.min() for x in all_x)),float(max(x.max() for x in all_x))])
    if spec.get('x_scale')=='log10' and 'x_range' in spec: xr=np.log10(xr)
    traces=[]
    for s,x in zip(spec['series'],all_x):
        for field in ('column','lower','upper'):
            if field not in s: continue
            y=column(rows,s[field])+float(s.get('offset',0))
            if spec.get('y_scale')=='log10':
                if np.any(y<=0):raise ValueError('Log Y requires positive data in every series')
                y=np.log10(y)
            dx,dy=pchip_connection(x,y,spec.get('connection_factor',16)) if spec.get('connection')=='pchip' else (x,y)
            # Sample each segment as well as nodes, including acquisition loops.
            t=np.linspace(0,1,9)
            traces.append((dx[:-1,None]+np.diff(dx)[:,None]*t,dy[:-1,None]+np.diff(dy)[:,None]*t) if len(dx)>1 else (dx[:,None],dy[:,None]))
        if 'lower' in s and 'upper' in s:
            lo=column(rows,s['lower'])+float(s.get('offset',0));hi=column(rows,s['upper'])+float(s.get('offset',0))
            if spec.get('y_scale')=='log10':lo,hi=np.log10(lo),np.log10(hi)
            t=np.linspace(0,1,9)
            traces.append((np.broadcast_to(x[:,None],(len(x),len(t))),lo[:,None]+(hi-lo)[:,None]*t))
    low=min(float(y.min()) for _,y in traces); high=max(float(y.max()) for _,y in traces)
    pad=(high-low)*.05 if high>low else (abs(low)*.05 if low else .05)
    yr=spec.get('y_range',[low-pad,high+pad])
    if spec.get('y_scale')=='log10' and 'y_range' in spec:yr=np.log10(yr)
    visible=[s for s in spec['series'] if s.get('legend',True)]
    columns=spec.get('legend_columns',1)
    width=min(.94 if columns>1 else .78,max(.26,.18+.030*max((len(s['label']) for s in visible),default=0))*columns)
    height=min(.80,.03+.11*math.ceil(len(visible)/columns))
    costs={}
    for corner in ('upper right','upper left','lower right','lower left'):
        l,r=(.98-width,.98) if 'right' in corner else (.02,.02+width)
        b,u=(.98-height,.98) if 'upper' in corner else (.02,.02+height)
        def normalized(values,bounds):
            span=float(bounds[1])-float(bounds[0])
            if span<0 or not math.isfinite(span):raise ValueError('Legend axis span must be finite and nonnegative')
            return (values-bounds[0])/span if span else np.full_like(values,.5)
        costs[corner]=sum(int(np.count_nonzero((xx>=l)&(xx<=r)&(yy>=b)&(yy<=u))) for xx,yy in
                          [(normalized(a,xr),normalized(b,yr)) for a,b in traces])
    return min(costs,key=costs.get),width,height,costs


def density(values, grid, bandwidth):
    # Gaussian KDE, with an explicit bandwidth in the observable's units.
    delta = (grid[:, None] - values[None, :]) / bandwidth
    return np.exp(-0.5 * delta * delta).mean(axis=1) / (bandwidth * math.sqrt(2 * math.pi))


def raincloud_geometry(rows, spec):
    key, value_key = spec["group"], spec["value"]
    if any(key not in row or not str(row[key]).strip() for row in rows):
        raise ValueError('Missing or empty raincloud group column: '+key)
    observed = list(dict.fromkeys(row[key] for row in rows))
    order = spec.get("order", observed)
    if len(set(order)) != len(order) or set(order) != set(observed):
        raise ValueError("Raincloud order must contain each observed group once")
    values = {group: column([row for row in rows if row[key] == group], value_key) for group in order}
    scott=spec['bandwidth']=='scott'
    fixed=None if scott else numeric(spec['bandwidth'],'bandwidth')
    bandwidths={g:(float(np.std(v,ddof=1)*len(v)**(-.2)) if len(v)>=3 and np.ptp(v)>0 else None) if scott else fixed for g,v in values.items()}
    if any(not math.isfinite(v) or v<=0 for v in bandwidths.values() if v is not None):
        raise ValueError("bandwidth must be positive, in observable units")
    seed = spec.get("seed", 1729)
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    shape = spec.get("cloud_shape", "half")
    support = spec.get("cloud_support", "kde")
    if support not in ("kde", "observed") or type(spec.get("summary", False)) is not bool:
        raise ValueError("cloud_support must be kde/observed and summary boolean")
    if spec.get('density_scale','shared') not in ('shared','width') or type(spec.get('cloud_fill',False)) is not bool:
        raise ValueError('density_scale must be shared/width and cloud_fill boolean')
    if shape not in ("half", "full") or spec.get("orientation", "horizontal") not in ("horizontal", "vertical"):
        raise ValueError("cloud_shape half/full; orientation horizontal/vertical")
    if 'point_cloud_gap' in spec and shape != 'half':
        raise ValueError('point_cloud_gap applies only to half clouds')
    point_gap=numeric(spec.get('point_cloud_gap',0.32),'point_cloud_gap')
    if not 0.06 <= point_gap <= 0.45:
        raise ValueError('point_cloud_gap must be 0.06..0.45 in group-axis units')
    all_values = np.concatenate(list(values.values()))
    bounds = spec.get("bounds")
    if bounds is not None:
        bounds=[numeric(v,'bounds') for v in bounds]
        if len(bounds) != 2 or bounds[1] <= bounds[0]:
            raise ValueError("bounds must be finite [lower, upper]")
        if all_values.min() < bounds[0] or all_values.max() > bounds[1]:
            raise ValueError("Observations fall outside the declared physical bounds")
        grid = np.linspace(*bounds, 512)
    clouds, grids = {}, {}
    for group, array in values.items():
        if len(array) < 3 or np.ptp(array) == 0:
            clouds[group] = None
            grids[group] = np.array([])
            continue
        local_bandwidth=bandwidths[group]
        if support=='observed':
            grid=np.linspace(float(array.min()),float(array.max()),512)
            if (array.max()-array.min())/511>local_bandwidth/8:
                local=np.concatenate([v+local_bandwidth*np.linspace(-4,4,65) for v in np.unique(array)])
                grid=np.unique(np.r_[grid,local[(local>=array.min())&(local<=array.max())],array])
        elif bounds is not None:
            # Resolve narrow kernels even when the physical domain is broad.
            local=np.concatenate([v+local_bandwidth*np.linspace(-4,4,65) for v in np.unique(array)])
            grid=np.unique(np.r_[np.linspace(*bounds,512),local[(local>=bounds[0])&(local<=bounds[1])],array])
        else:
            grid=np.unique(np.r_[np.linspace(array.min()-4*local_bandwidth,array.max()+4*local_bandwidth,512),array])
            if (grid[-1]-grid[0])/511>local_bandwidth/8:
                local=np.concatenate([v+local_bandwidth*np.linspace(-4,4,65) for v in np.unique(array)])
                grid=np.unique(np.r_[grid,local])
        if len(grid)*len(array)>20000000:
            raise ValueError('KDE grid exceeds 20 million evaluations; use an explicit upstream density method')
        curve = density(array, grid, local_bandwidth)
        if bounds is not None:
            curve += density(2 * bounds[0] - array, grid, local_bandwidth)
            curve += density(2 * bounds[1] - array, grid, local_bandwidth)
            # Analytic mass avoids zero quadrature when a coarse global grid
            # misses a narrow kernel. No density clipping or shape modification.
            centers=np.r_[array,2*bounds[0]-array,2*bounds[1]-array]
            mass=sum(.5*(math.erf((bounds[1]-v)/(local_bandwidth*math.sqrt(2)))-
                          math.erf((bounds[0]-v)/(local_bandwidth*math.sqrt(2)))) for v in centers)/len(array)
            if not math.isfinite(mass) or mass<=0:raise ValueError('Reflected KDE mass is not resolvable')
            curve /= mass
        if not np.all(np.isfinite(curve)) or float(curve.max())<=0:
            raise ValueError('KDE is not numerically resolvable; revise bandwidth or units explicitly')
        clouds[group] = curve
        grids[group] = grid
    peak = max([float(curve.max()) for curve in clouds.values() if curve is not None] or [1])
    result = []
    for index, group in enumerate(order, 1):
        array = values[group]
        # Type-7 quantiles; equal values and outliers remain individual points.
        q1, median, q3 = np.quantile(array, [0.25, 0.5, 0.75], method="linear")
        iqr = q3 - q1
        inside = array[(array >= q1 - 1.5 * iqr) & (array <= q3 + 1.5 * iqr)]
        whiskers = [float(inside.min()), float(inside.max())]
        digest = hashlib.sha256((str(seed) + ":" + group).encode()).digest()
        rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
        # Keep the established default bytes; an explicit gap translates only
        # the group coordinate, never observations, KDE or random jitter.
        point_center=index-0.22 if point_gap==0.32 else index+0.10-point_gap
        jitter = (point_center + rng.uniform(-0.045, 0.045, len(array))) if shape == "half" else index + rng.uniform(-0.10, 0.10, len(array))
        curve = clouds[group]
        grid = grids[group]
        group_peak = peak if spec.get('density_scale','shared')=='shared' else (float(curve.max()) if curve is not None else peak)
        top = None if curve is None else (index + 0.10 + 0.30 * curve / group_peak if shape == "half" else index + 0.26 * curve / group_peak)
        bottom = None if curve is None else (np.full_like(grid, index + 0.10) if shape == "half" else index - 0.26 * curve / group_peak)
        segments = []
        if curve is not None:
            # Gaussian KDE tails are a property of the disclosed estimator.
            # cut=0 is only a visible extent option; never taper or split the
            # density to imitate an observation-free interval.
            segments.append({"grid":grid,"top":top,"bottom":bottom})
        result.append({
            "group": group, "index": index, "values": array, "jitter_y": jitter,
            "bandwidth": bandwidths[group],
            "q1": float(q1), "median": float(median), "q3": float(q3), "whiskers": whiskers,
            "grid": grid, "density": curve,
            "cloud_top": top, "cloud_bottom": bottom,
            "segments": segments,
            "kde_status": "omitted_small_or_constant_sample" if curve is None else "computed",
        })
    return result


class Book:
    def __init__(self, name):
        self.name, self.headers, self.columns = name, [], []

    def add_pair(self, label, x, y):
        label = label + "_s" + str(len(self.columns) // 2 + 1)
        self.headers.extend([label + "_x", label + "_y"])
        self.columns.extend([list(map(float, x)), list(map(float, y))])
        if len(self.columns[-1]) != len(self.columns[-2]):
            raise ValueError("XY lengths differ")
        return len(self.columns) - 1, len(self.columns)

    def export(self):
        if any(not np.all(np.isfinite(col)) for col in self.columns):
            raise ValueError('Derived geometry contains non-finite values; no outputs created')
        length = max(map(len, self.columns))
        rows = [[col[i] if i < len(col) else None for col in self.columns] for i in range(length)]
        return {"name": self.name, "headers": self.headers, "rows": rows}


def add_series(commands, book, graph_id, pair, *, first=False, scatter=False, color="#315D85", width=1.5,
               line_style="solid", marker_size=4.5):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("Colors must be six-digit hex")
    target = "[<new name:=" + graph_id + ">]" if first else "1!"
    x, y = pair
    commands.append("plotxy iy:=[%s]Sheet1!(%d,%d) plot:=%d ogl:=%s" %
                    (book.name, x, y, 201 if scatter else 200, target))
    plot_index = sum(command.startswith("plotxy") for command in commands)
    curve = "Curve" + str(plot_index)
    commands.extend([
        "layer -gu",
        "range %s=!%d" % (curve, plot_index),
        "set %s -pf 0" % curve,
        "set %s -c color(%s)" % (curve, lt_string(color)),
        "set %s -cl color(%s)" % (curve, lt_string(color)),
        "set %s -w %d" % (curve, round(width * 500)),
        "set %s -d %d" % (curve, STYLE.LINE_IDS[line_style]),
    ])
    if scatter:
        commands.append("set %s -csf color(%s)" % (curve, lt_string(color)))
        commands.append("set %s -k 2" % curve)
        commands.append("set %s -z %s" % (curve, num(marker_size)))
    return plot_index


def prepare_plot(spec, rows, index, style, *, native_text=True):
    common = {"id", "kind", "csv", "synthetic", "title", "labels", "caption", "x_range", "y_range", "x_tick_step", "y_tick_step", "equal_xy", "x_scale", "y_scale", "legend_columns"}
    options = {
        "line": {"x", "series", "connect_order", "connection", "connection_factor", "y_ticks"},
        "line_symbol": {"x", "series", "connect_order", "connection", "connection_factor", "y_ticks"},
        "scatter": {"x", "series", "connect_order", "connection", "connection_factor", "y_ticks"},
        "bar": {"x", "series", "stacked", "x_tick_labels"},
        "heatmap": {"x", "y", "z", "color_range", "center", "cmap", "color_levels", "interpolation", "y_tick_labels"},
        "raincloud": {"group", "value", "order", "bandwidth", "seed", "bounds", "cloud_shape", "orientation", "group_labels", "summary", "cloud_support", "density_scale", "cloud_fill", "point_cloud_gap"},
    }
    if not isinstance(spec,dict) or spec.get('kind') not in options or set(spec) - (common | options[spec["kind"]]):
        raise ValueError("Unsupported plot kind or plot configuration key")
    if 'legend_columns' in spec and spec['kind'] not in ('line','line_symbol','scatter','bar'):
        raise ValueError('legend_columns requires an XY or stacked-bar legend')
    required={'x','series'} if spec['kind'] in ('line','line_symbol','scatter','bar') else {'x','y','z','color_range'} if spec['kind']=='heatmap' else {'group','value','bandwidth'}
    missing=required-set(spec)
    if missing:raise ValueError('Missing plot settings: '+', '.join(sorted(missing)))
    if 'series' in required and (not isinstance(spec['series'],list) or not spec['series']):
        raise ValueError('series must be a nonempty list')
    if 'series' in required:
        if type(spec.get('legend_columns',1)) is not int or spec.get('legend_columns',1) not in (1,2):
            raise ValueError('legend_columns must be integer1 or2')
        for s in spec['series']:
            if not isinstance(s,dict) or type(s.get('legend',True)) is not bool:
                raise ValueError('series legend must be boolean')
            if any(not isinstance(s.get(key),str) or not s[key].strip() for key in ('column','label')):
                raise ValueError('Each series requires nonempty column and label strings')
            if 'id' in s and (not isinstance(s['id'],str) or not s['id'].strip()):
                raise ValueError('Series id must be a nonempty string')
            if 'uncertainty_definition' in s and (not isinstance(s['uncertainty_definition'],str) or not s['uncertainty_definition'].strip()):
                raise ValueError('uncertainty_definition must be a nonempty string')
        if not any(s.get('legend',True) for s in spec['series']):
            raise ValueError('At least one visible series legend is required')
    if 'synthetic' in spec and type(spec['synthetic']) is not bool:
        raise ValueError('synthetic must be boolean')
    if 'y_ticks' in spec:
        if type(spec['y_ticks']) is not bool:
            raise ValueError('y_ticks must be boolean')
        if not spec['y_ticks'] and 'y_tick_step' in spec:
            raise ValueError('y_tick_step requires visible Y ticks')
    if 'connection_factor' in spec and spec.get('connection')!='pchip':
        raise ValueError('connection_factor requires pchip')
    if spec['kind']=='raincloud' and spec.get('x_scale','linear')!='linear':
        raise ValueError('Log raincloud axes require a separate density/axis adapter')
    if spec.get('y_scale','linear') not in ('linear','log10'):
        raise ValueError('y_scale must be linear or log10')
    if spec.get('y_scale')=='log10' and spec['kind'] not in ('line','line_symbol','scatter'):
        raise ValueError('Log Y currently requires an XY recipe')
    required_labels={'x','y','color'} if spec['kind']=='heatmap' else {'x','y'}
    if not isinstance(spec.get('labels'),dict) or set(spec['labels'])!=required_labels or any(not isinstance(v,str) or not v.strip() for v in spec['labels'].values()):
        raise ValueError('labels must supply nonempty '+','.join(sorted(required_labels)))
    graph_id = "Plot" + str(index)
    book = Book("Data" + str(index))
    commands, metadata = [], {"kind": spec["kind"], "row_count": len(rows)}
    metadata['display_text'] = plot_text(spec,rows)
    for text in metadata['display_text']:
        plain_text(text)
    native_ready=not any('%' in text for text in metadata['display_text'])
    if native_text and not native_ready:
        raise ValueError('Percent labels require a separately validated native text adapter; use Python for literal percent')
    # Python still needs identical validated worksheets/geometry. Unavailable
    # native strings use inert placeholders internally; no such commands leave
    # this function. Never publish a native plan with altered display labels.
    def quote_text(value):
        return '""' if not native_ready and '%' in str(value) else lt_string(value)
    def label_text(value, native=True):
        return '""' if not native_ready and '%' in str(value) else display_label(value,native)
    if "caption" in spec:
        if not isinstance(spec["caption"], str) or not spec["caption"].strip():
            raise ValueError("Caption must be a nonempty string")
        metadata["caption"] = spec["caption"]
    colors = style["colors"]["palette"]
    if not colors or any(not re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in colors):
        raise ValueError("Provide a nonempty palette of six-digit hex colors")
    if spec["kind"] in ("line", "scatter", "line_symbol"):
        corner,key_width,key_height,key_costs=legend_corner(spec,rows)
        metadata['legend']={'corner':corner,'overlap_scores':key_costs}
        legend = []
        connect_order = spec.get("connect_order", "increasing")
        if connect_order not in ("increasing", "acquisition"):
            raise ValueError("connect_order must be increasing or acquisition")
        metadata.update({"connect_order": connect_order, "display_offsets": []})
        for si, series in enumerate(spec["series"]):
            if set(series) - {"x", "legend", "column", "id", "label", "color", "lower", "upper", "uncertainty_definition", "offset", "kind"}:
                raise ValueError("Unsupported series configuration key")
            x = column(rows, series.get('x',spec['x']))
            series_kind = series.get("kind", spec["kind"])
            if series_kind not in ("line", "scatter", "line_symbol"):
                raise ValueError("Unsupported series kind")
            if series_kind != "scatter" and connect_order == "increasing" and not np.all(np.diff(x) > 0):
                raise ValueError("Connected curves require strictly increasing X; sort explicitly upstream")
            raw_y = column(rows, series["column"])
            offset = numeric(series.get("offset", 0),'series offset')
            if not math.isfinite(offset):
                raise ValueError("Display offset must be finite")
            y = raw_y + offset
            if offset:
                book.add_pair("raw_" + series["column"], x, raw_y)
            metadata["display_offsets"].append({"column": series["column"], "offset": offset})
            appearance = STYLE.series(style, series.get("id", series["column"]), si, series.get("color"))
            color = appearance["color"]
            has_band = "lower" in series or "upper" in series
            if has_band:
                if connect_order == "acquisition" or not np.all(np.diff(x)>0):
                    raise ValueError("Bands require increasing X; separate acquisition branches first")
                if 'lower' not in series or 'upper' not in series:
                    raise ValueError('Bands require both lower and upper columns')
                if not series.get("uncertainty_definition"):
                    raise ValueError("Define the uncertainty band; do not silently call it a CI")
                lo, hi = column(rows, series["lower"]) + offset, column(rows, series["upper"]) + offset
                if np.any(lo > y) or np.any(hi < y):
                    raise ValueError("Uncertainty bounds must contain their central values")
                p = add_series(commands, book, graph_id, book.add_pair("upper", x, hi),
                               first=not commands, color=color)
                add_series(commands, book, graph_id, book.add_pair("lower", x, lo), color=color)
                commands.extend(["set Curve%d -pf 1" % p, "set Curve%d -pfv 8" % p,
                                 "set Curve%d -pfn 1" % p, "set Curve%d -pfb color(%s)" % (p, quote_text(color)),
                                 "layer.plot%d.transparency=75" % p, "set Curve%d -l 0" % (p + 1)])
            if spec.get("connection", "straight") not in ("straight", "pchip"):
                raise ValueError("Unsupported connection")
            draw_x, draw_y = x, y
            if spec.get("connection") == "pchip":
                if series_kind != "line_symbol" or has_band or connect_order != "increasing":
                    raise ValueError("PCHIP display requires increasing line_symbol without bands")
                draw_x, draw_y = pchip_connection(x,y,spec.get("connection_factor",16))
                metadata["display_connection"] = "PCHIP; original nodes retained; no fit, no additional images, node-based barrier"
            central = add_series(commands, book, graph_id, book.add_pair(series["label"], draw_x, draw_y),
                                 first=not commands, scatter=series_kind == "scatter", color=color,
                                 width=appearance["width_pt"], line_style=appearance["line_style"], marker_size=appearance["marker_size_pt"])
            if series.get('legend',True):
                legend.append((central, series["label"]))
            if series_kind == "line_symbol":
                add_series(commands, book, graph_id, book.add_pair("points", x, y), scatter=True, color=color,
                           marker_size=appearance["marker_size_pt"])
        books = [book.export()]
        metadata["series"] = spec["series"]
    elif spec['kind']=='bar':
        if spec.get('stacked') is not True or spec.get('x_scale','linear')!='linear' or spec.get('y_scale','linear')!='linear':
            raise ValueError('Bar currently requires explicit positive linear stacked columns')
        x=column(rows,spec['x']);tick_labels=spec.get('x_tick_labels')
        if not np.array_equal(x,np.arange(len(x))) or len(x)<2 or not isinstance(tick_labels,list) or len(tick_labels)!=len(x):
            raise ValueError('Stacked bar uses explicit consecutive category positions and matching labels')
        if any(not isinstance(t,str) or not t or any(c.isspace() or c in ('\\";$%' if native_text else '\\";$') for c in t) for t in tick_labels):
            raise ValueError('Stacked bar tick labels must be nonempty single safe tokens')
        if len(spec['series'])<2 or len(spec['series'])>7:raise ValueError('Stacked bar supports2..7 declared components')
        corner,key_width,key_height,key_costs=legend_corner(spec,rows);legend=[]
        book.headers=[spec['x']];book.columns=[x.tolist()]
        for i,s in enumerate(spec['series']):
            if set(s)-{'column','label','color','id','legend'}:raise ValueError('Unsupported stacked-bar series field')
            y=column(rows,s['column'])
            if np.any(y<0):raise ValueError('Stacked bar components must be nonnegative; never clip signs')
            book.headers.append(s['column']);book.columns.append(y.tolist())
            if s.get('legend',True):legend.append((i+1,s['label']))
        commands=['plotxy iy:=[%s]Sheet1!(1,2:%d) plot:=213 ogl:=[<new name:=%s>]'%(book.name,len(book.headers),graph_id),
                  'layer -g 1 '+str(len(spec['series'])),'range Curve1=!1','set Curve1 -gm 1']
        for i,s in enumerate(spec['series'],1):
            appearance=STYLE.series(style,s.get('id',s['column']),i-1,s.get('color'));color=quote_text(appearance['color']);c='Curve'+str(i)
            commands.extend(['range '+c+'=!'+str(i),'set '+c+' -c color('+color+')','set '+c+' -cl color('+color+')',
                             'set '+c+' -pfb color('+color+')','set '+c+' -pbc color('+color+')',
                             'set '+c+' -pbs 0','set '+c+' -vw 0','set '+c+' -vg 38'])
        commands.append('layer -b s 1');books=[book.export()]
        metadata.update(series=spec['series'],category_labels=tick_labels,category_positions=x.tolist(),stacked=True,
                        legend={'corner':corner,'overlap_scores':key_costs})
    elif spec["kind"] == "heatmap":
        xs, ys, grid, raw_grid, interpolation = heatmap_display(rows, spec)
        if 'y_tick_labels' in spec:
            tick_labels=spec['y_tick_labels']
            if not isinstance(tick_labels,list) or len(tick_labels)!=len(ys) or not np.array_equal(ys,np.arange(len(ys))):
                raise ValueError('Categorical heatmap Y needs one label per consecutive row index starting at zero')
            if any(not isinstance(t,str) or not t or any(c.isspace() or c in ('\\";$%' if native_text else '\\";$') for c in t) for t in tick_labels) or len(set(tick_labels))!=len(tick_labels):
                raise ValueError('Categorical heatmap labels must be unique safe tokens')
            if interpolation!='none' or 'y_tick_step' in spec or 'y_range' in spec:
                raise ValueError('Categorical heatmap Y forbids cross-row interpolation or overridden Y geometry')
            metadata['category_y_labels']=tick_labels
            metadata['category_y_positions']=ys.tolist()
        limits = [numeric(v,'color_range') for v in spec["color_range"]]
        if len(limits) != 2 or not all(map(math.isfinite, limits)) or limits[1] <= limits[0]:
            raise ValueError("color_range must be finite [min, max]")
        if grid.min() < limits[0] or grid.max() > limits[1]:
            raise ValueError("Color range clips data; revise it or disclose clipping before plotting")
        if "center" in spec:
            center = numeric(spec["center"], "center")
            if not limits[0] < center < limits[1]:
                raise ValueError("center must lie strictly inside color_range")
            if not math.isclose(center, limits[0] / 2 + limits[1] / 2):
                raise ValueError("Native v1 requires a centered symmetric color range; custom nonlinear levels need a separate adapter")
        matrix = [[0.0] + xs.tolist()] + [[float(y)] + row.tolist() for y, row in zip(ys, grid)]
        books = [{"name": book.name, "headers": ["coordinate"] + ["z" + str(i) for i in range(len(xs))],
                  "rows": matrix}]
        if interpolation != "none":
            rx, ry, rz = raw_grid
            books.insert(0, {"name": book.name + "Raw", "headers": ["coordinate"] + ["z" + str(i) for i in range(len(rx))],
                             "rows": [[0.0] + rx.tolist()] + [[float(y)] + row.tolist() for y, row in zip(ry, rz)]})
        commands = [
            "plotvm irng:=[%s]Sheet1!2[2]:%d[%d] format:=1 rowpos:=2 colpos:=2 type:=105 ogl:=[<new template:=Heat_Map name:=%s>]" %
            (book.name, len(xs) + 1, len(ys) + 1, graph_id),
        ]
        # Apply the color contract after layer -a: auto-rescale otherwise
        # silently restores the data-dependent Z range on Origin 2021.
        levels = spec.get("color_levels", 16)
        if type(levels) is not int or not 2 <= levels <= 256:
            raise ValueError("color_levels must be an integer 2..256")
        color_commands = [
            "layer.cmap.zmin=" + num(limits[0]), "layer.cmap.zmax=" + num(limits[1]),
            "layer.cmap.numcolors=" + str(levels), "layer.cmap.setLevels(1)", "layer.cmap.updateScale()",
        ]
        from matplotlib.colors import to_hex
        palette = [to_hex(color_map(spec)(v)) for v in np.linspace(0, 1, levels)]
        color_commands[-1:-1] = ["layer.cmap.color%d=color(%s)" % (i, quote_text(color)) for i, color in enumerate(palette, 1)]
        color_commands.extend(["label -r Spectrum1",
                               "layer.x.label.rotate=0",
                               "label -n ScaleTitle " + quote_text(spec["labels"]["color"])])
        metadata.update({"grid_shape": list(grid.shape), "matrix_orientation": "rows=Y, columns=X",
                         "source_grid_shape": list(raw_grid[2].shape), "color_levels": levels,
                         "aggregation": "none", "interpolation": interpolation, "color_range": limits,
                         "cmap":spec.get('cmap',load_json(COLORMAP_PATH)['default']),
                         "colormaps_sha256":sha256(COLORMAP_PATH),
                         "colorbar_palette": palette, "colorbar_labels":colorbar_labels(limits),
                         "colorbar": "embedded palette bitmap + editable labels"})
    elif spec["kind"] == "raincloud":
        groups = raincloud_geometry(rows, spec)
        full = spec.get("cloud_shape", "half") == "full"
        vertical = spec.get("orientation", "horizontal") == "vertical"
        pair = lambda label, value, position: book.add_pair(label, position, value) if vertical else book.add_pair(label, value, position)
        for group in groups:
            gi = group["index"]
            appearance = STYLE.series(style, group["group"], gi - 1)
            color = appearance["color"]
            for segment in group['segments']:
                if vertical and spec.get('cloud_fill',False):
                    # A closed source-bound polygon gives the exact KDE region.
                    # Origin 2021 also strokes its implicit baseline closure;
                    # zero stroke preserves fill without artificial drop lines.
                    px=np.r_[segment['top'],segment['bottom'][::-1],segment['top'][:1]]
                    py=np.r_[segment['grid'],segment['grid'][::-1],segment['grid'][:1]]
                    p=add_series(commands,book,graph_id,book.add_pair('cloud_polygon',px,py),
                                 first=not commands,color=color,width=0)
                    commands.extend(['set Curve%d -pf 1'%p,'set Curve%d -pfv 1'%p,
                                     'set Curve%d -pfb color(%s)'%(p,quote_text(color)),
                                     'layer.plot%d.transparency=78'%p])
                    continue
                p = add_series(commands, book, graph_id, pair("cloud", segment["grid"], segment["top"]),
                               first=not commands, color=color, width=0.6)
                add_series(commands, book, graph_id, pair("baseline", segment["grid"], segment["bottom"]), color=color, width=0.6)
                if spec.get('cloud_fill',False):
                    commands.extend(["set Curve%d -pf 1" % p, "set Curve%d -pfv 8" % p, "set Curve%d -pfn %d" % (p, 2 if vertical else 1),
                                 "set Curve%d -pfb color(%s)" % (p, quote_text(color)),
                                 "layer.plot%d.transparency=78" % p])
                if not full:
                    commands.append("set Curve%d -l 0" % (p + 1))
            q1, q3, median = group["q1"], group["q3"], group["median"]
            summary = gi + 0.36 if full else gi
            if spec.get('summary',False):
                add_series(commands, book, graph_id, pair("box", [q1, q3, q3, q1, q1],
                       [summary - 0.035, summary - 0.035, summary + 0.035, summary + 0.035, summary - 0.035]),
                       first=not commands, color=color, width=0.6)
                add_series(commands, book, graph_id, pair("median", [median, median], [summary - 0.035, summary + 0.035]), color="#222222", width=0.9)
                add_series(commands, book, graph_id, pair("whiskers", group["whiskers"], [summary, summary]), color=color, width=0.6)
                for endpoint in group["whiskers"]:
                    add_series(commands, book, graph_id, pair("cap", [endpoint, endpoint], [summary - 0.025, summary + 0.025]), color=color, width=0.6)
            add_series(commands, book, graph_id, pair("observations", group["values"], group["jitter_y"]), scatter=True, color=color,
                       marker_size=appearance["marker_size_pt"])
        books = [book.export()]
        metadata.update({
            "bandwidth": spec['bandwidth'], "effective_bandwidths":{g['group']:g['bandwidth'] for g in groups}, "seed": int(spec.get("seed", 1729)),
            "cloud_shape": "full" if full else "half", "orientation": "vertical" if vertical else "horizontal",
            "bounds": spec.get("bounds"), "density_scaling": spec.get('density_scale','shared'),
            "summary_visible": spec.get('summary',False), "cloud_support": spec.get('cloud_support','kde'),
            "support_disclosure": "Gaussian KDE; observed view is cut=0 at each raw min/max. No taper, gap splitting, denoising or dropped observations. Density between observations is estimator output, not fabricated samples.",
            "quantiles": "type-7 linear", "whiskers": "observed endpoints within 1.5 IQR",
            "groups": [{"group": g["group"], "n": len(g["values"]), "q1": g["q1"], "median": g["median"],
                        "q3": g["q3"], "whiskers": g["whiskers"], "kde_status": g["kde_status"]} for g in groups],
        })
        if 'point_cloud_gap' in spec:
            metadata['point_cloud_gap']=numeric(spec['point_cloud_gap'],'point_cloud_gap')
        # Create group labels after the final rescale/layout; 2021's label
        # position then stays attached to the intended layer frame.
        # Group scale is applied after auto-rescaling, in the chosen orientation.
    else:
        raise ValueError("Script supports line, line_symbol, scatter, heatmap and raincloud")
    font = style["font"]["family"]
    axes, fonts, figure = style["axes"], style["font"], style["figure"]
    background = "color(%s)" % quote_text(figure["background_color"])
    axis_color = "color(%s)" % quote_text(axes["color"])
    grid = str(int(axes["major_grid"]))
    tick_direction = "1" if axes["tick_direction"] == "in" else "2"
    commands.extend([
        "page.baseColor=" + background, "layer.color=" + background, "layer -a", "layer.x.grid.show=" + grid, "layer.y.grid.show=" + grid,
        "page.width=page.resx*" + num(figure["width_mm"] / 25.4), "page.height=page.resy*" + num(figure["height_mm"] / 25.4),
        "layer.unit=1", "layer.left=22", "layer.top=18", "layer.width=" + ("55" if spec["kind"] == "heatmap" else "72"), "layer.height=62",
        "label -r XB", "label -r YL",
        "label -xb " + label_text(spec["labels"]["x"],True), "label -yl " + label_text(spec["labels"]["y"],True),
        "xb.font=font(%s)" % quote_text(font), "yl.font=font(%s)" % quote_text(font),
        "xb.fsize=" + num(fonts["axis_title_size_pt"]), "yl.fsize=" + num(fonts["axis_title_size_pt"]),
        "layer.x.label.fsize=" + num(fonts["tick_size_pt"]), "layer.y.label.fsize=" + num(fonts["tick_size_pt"]),
        "layer.x.label.font=font(%s)" % quote_text(font), "layer.y.label.font=font(%s)" % quote_text(font),
        "layer.x.color=" + axis_color, "layer.y.color=" + axis_color,
        "layer.x.thickness=" + num(axes["width_pt"]), "layer.y.thickness=" + num(axes["width_pt"]),
        "layer.x.ticks=" + tick_direction, "layer.y.ticks=" + tick_direction,
        "layer.tickl=2", "layer.tickw=" + num(axes["width_pt"]),
        "axis -ps X A " + ("3" if axes["frame"] == "full" else "1"),
        "axis -ps X L 1",
        "axis -ps Y A " + ("3" if axes["frame"] == "full" else "1"),
        "axis -ps Y L 1",
        "layer.x2.ticks=0", "layer.y2.ticks=0",
        "label -r Legend",
        "xb.attach=2", "yl.attach=2", "yl.rotate=90",
        "xb.x=layer.x.from+0.5*(layer.x.to-layer.x.from)", "xb.y=layer.y.from-0.23*(layer.y.to-layer.y.from)",
        "yl.x=layer.x.from-0.27*(layer.x.to-layer.x.from)", "yl.y=layer.y.from+0.5*(layer.y.to-layer.y.from)",
    ])
    if spec["kind"] in ("line", "scatter", "line_symbol", "bar"):
        for li,(i,label) in enumerate(legend,1):
            name="SeriesKey"+str(li)
            text="\\l(%d) %s" % (i,label_text(label,native=True)[1:-1])
            commands.extend(['label -n '+name+' "'+text+'"',name+'.fsize='+num(fonts['legend_size_pt']),
                             name+'.font=font(%s)'%quote_text(font),name+'.attach=2'])
    if spec.get("title"):
        commands.extend(["label -n Title " + quote_text(spec["title"]), "Title.fsize=" + num(fonts["title_size_pt"]),
                         "Title.attach=2",
                         "Title.font=font(%s)" % quote_text(font),
                         "Title.x=layer.x.from+0.5*(layer.x.to-layer.x.from)",
                         "Title.y=layer.y.from+1.10*(layer.y.to-layer.y.from)"])
    if spec["kind"] == "heatmap":
        commands.extend(color_commands)
        commands.extend(["ScaleTitle.fsize=" + num(fonts["axis_title_size_pt"]), "ScaleTitle.rotate=90",
                         "ScaleTitle.font=font(%s)" % quote_text(font),
                         "ScaleTitle.attach=2", "ScaleTitle.x=layer.x.from+1.34*(layer.x.to-layer.x.from)",
                         "ScaleTitle.y=layer.y.from+0.5*(layer.y.to-layer.y.from)"])
        for i, value in enumerate(colorbar_labels(limits), 1):
            commands.extend(["label -n CBT%d %s" % (i, quote_text(value)),
                             "CBT%d.attach=2" % i, "CBT%d.fsize=%s" % (i, num(fonts["annotation_size_pt"])),
                             "CBT%d.font=font(%s)" % (i, quote_text(font)),
                             "CBT%d.x=layer.x.from+1.18*(layer.x.to-layer.x.from)" % i,
                             "CBT%d.y=layer.y.from+%s*(layer.y.to-layer.y.from)" % (i, num((i-1) / 4))])
    if spec["kind"] == "raincloud":
        grouping = "x" if vertical else "y"
        commands.extend(["layer.%s.from=0.55" % grouping, "layer.%s.to=%s" % (grouping, num(len(groups) + (0.60 if vertical else 0.80))),
                         "layer.%s.showLabels=0" % grouping, "layer.%s2.showLabels=0" % grouping, "layer.%s.ticks=0" % grouping])
        for g in groups:
            label = spec.get("group_labels", {}).get(g["group"], g["group"])
            commands.extend(["label -n Group%d %s" % (g["index"], quote_text(label + " (n=" + str(len(g["values"])) + ")")),
                             "Group%d.fsize=%s" % (g["index"], num(fonts["legend_size_pt"])),
                             "Group%d.attach=2" % g["index"],
                             ("Group%d.x=%s" % (g["index"], num(g["index"]))) if vertical else "Group%d.x=layer.x.from+0.23*(layer.x.to-layer.x.from)" % g["index"],
                             ("Group%d.y=layer.y.from-0.08*(layer.y.to-layer.y.from)" % g["index"]) if vertical else "Group%d.y=%s" % (g["index"], num(g["index"] + 0.60)),
                             "Group%d.font=font(%s)" % (g["index"], quote_text(font))])
    for axis in ("x", "y"):
        if axis + "_range" in spec:
            start, end = [numeric(v,axis+'_range') for v in spec[axis + "_range"]]
            if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                raise ValueError("Invalid axis range")
            commands.extend(["layer.%s.from=%s" % (axis, num(start)), "layer.%s.to=%s" % (axis, num(end))])
    # Axis-title objects can move when the grouping/range is changed in 2021.
    # Place them after the final scale, rather than retaining auto offsets.
    commands.extend(["xb.x=layer.x.from+0.5*(layer.x.to-layer.x.from)",
                     "xb.y=layer.y.from-0.23*(layer.y.to-layer.y.from)",
                     "yl.x=layer.x.from-0.27*(layer.x.to-layer.x.from)",
                     "yl.y=layer.y.from+0.5*(layer.y.to-layer.y.from)"])
    if spec["kind"] == "raincloud" and vertical:
        # The reserved XB object is auto-positioned beside custom group labels
        # on 2021. Use an ordinary text object with an explicit data anchor.
        commands.extend(["label -r XB", "label -n AxisTitleX " + quote_text(spec["labels"]["x"]),
                         "AxisTitleX.attach=2", "AxisTitleX.font=font(%s)" % quote_text(font),
                         "AxisTitleX.fsize=" + num(fonts["axis_title_size_pt"]),
                         "AxisTitleX.x=layer.x.from+0.5*(layer.x.to-layer.x.from)",
                         "AxisTitleX.y=layer.y.from-0.23*(layer.y.to-layer.y.from)"])
    for axis in ("x", "y"):
        if axis + "_tick_step" in spec:
            step = numeric(spec[axis + "_tick_step"],axis+'_tick_step')
            if not math.isfinite(step) or step <= 0:
                raise ValueError("Tick step must be finite and positive")
            commands.append("layer.%s.inc=%s" % (axis, num(step)))
    if "equal_xy" in spec and type(spec["equal_xy"]) is not bool:
        raise ValueError("equal_xy must be boolean")
    if spec.get("equal_xy"):
        if spec.get("x_scale","linear") != "linear" or spec.get('y_scale','linear') != 'linear':
            raise ValueError("Equal XY requires linear axes")
        if spec["kind"] not in ("line", "scatter", "line_symbol"):
            raise ValueError("equal_xy currently supports XY plots only")
        if not all(axis + "_range" in spec for axis in ("x", "y")):
            raise ValueError("equal_xy requires explicit x_range and y_range")
        dx = float(spec["x_range"][1]) - float(spec["x_range"][0])
        dy = float(spec["y_range"][1]) - float(spec["y_range"][0])
        width = min(72, 62 * figure["height_mm"] / figure["width_mm"] * dx / dy)
        height = width * figure["width_mm"] / figure["height_mm"] * dy / dx
        # The algebraic upper bound is62; roundoff can produce62+one ULP.
        if height>62. and math.isclose(height,62.,rel_tol=0.,abs_tol=1e-12):
            height=62.
        if not 15 <= height <= 62 or width < 15:
            raise ValueError("equal_xy geometry does not fit the current native page")
        commands.extend(["layer.width=" + num(width), "layer.left=" + num(22+(72-width)/2),
                         "layer.height=" + num(height), "layer.top=" + num(18 + (62-height)/2)])
    scale=spec.get("x_scale","linear")
    if scale not in ("linear","log10"):
        raise ValueError("x_scale must be linear or log10")
    if scale=="log10":
        xvalues=np.concatenate([column(rows,s.get('x',spec['x'])) for s in spec['series']]) if 'series' in spec else column(rows,spec['x'])
        if np.any(xvalues<=0) or "x_range" not in spec or min(spec["x_range"])<=0:
            raise ValueError("Log X requires positive data and explicit positive x_range")
        if "x_tick_step" in spec:
            raise ValueError("Log X uses one-decade increments, not linear x_tick_step")
        commands.extend(["@TL=0","layer.x.type=2","layer.x.inc=1","layer.x.minorTicks=8"])
        commands.extend(['layer.x.from='+num(spec['x_range'][0]),'layer.x.to='+num(spec['x_range'][1])])
        lower,upper=map(math.log10,spec['x_range'])
        if not lower.is_integer() or not upper.is_integer():
            raise ValueError("Log X power labels require decade endpoints")
        # Controlled integer exponents: Origin's rich text uses the real Arial
        # glyphs, including minus/zero missing from Arial's Unicode superscripts.
        labels=' '.join('10\\+(%d)' % i for i in range(int(lower),int(upper)+1))
        commands.extend(['layer.x.label.type=10','layer.x.label.string$="'+labels+'"'])
        metadata['x_scale']='log10';metadata['x_range']=spec['x_range']
        # Place decorations by layer-frame percentages, independent of log axes.
        xat=lambda fraction:'10^(log(layer.x.from)+'+num(fraction)+'*(log(layer.x.to)-log(layer.x.from)))'
        commands.extend(['xb.x='+xat(.5),'yl.x='+xat(-.27)])
        if spec.get('title'):
            commands.append('Title.x='+xat(.5))
        if spec['kind']=='heatmap':
            commands.extend(['label -p 134 50 -n ScaleTitle '+quote_text(spec['labels']['color']), 'ScaleTitle.attach=0', 'ScaleTitle.rotate=90'])
            for i,value in enumerate(colorbar_labels(limits),1):
                commands.extend(['label -p 118 %s -n CBT%d %s'%(num(100-25*(i-1)),i,quote_text(value)),'CBT%d.attach=0'%i])
    if spec['kind']=='bar':
        commands.extend(['layer.x.inc=1','layer.x.label.type=10','layer.x.label.string$="'+' '.join(spec['x_tick_labels'])+'"','layer -b s 1'])
    if spec['kind']=='heatmap' and 'y_tick_labels' in spec:
        commands.extend(['layer.y.from=-0.5','layer.y.to='+num(len(spec['y_tick_labels'])-.5),
                         'layer.y.inc=1','layer.y.label.type=10',
                         'layer.y.label.string$="'+' '.join(spec['y_tick_labels'])+'"'])
    if spec["kind"] in ("line", "scatter", "line_symbol", "bar"):
        cx=100*(.98-key_width) if 'right' in corner else 4
        top=8 if 'upper' in corner else 100*(.98-key_height)+5
        columns=spec.get('legend_columns',1);key_rows=math.ceil(len(legend)/columns)
        for li,(plot_index,label) in enumerate(legend,1):
            text='"\\l(%d) %s"'%(plot_index,label_text(label,True)[1:-1])
            col,row=divmod(li-1,key_rows)
            commands.extend(['label -p %s %s -n SeriesKey%d %s'%(num(cx+100*key_width*col/columns),num(top+10*row),li,text),'SeriesKey%d.attach=0'%li])
    # Origin 2021 auto-repositions the reserved YL label during export, ignoring
    # the requested x coordinate. An ordinary text object remains controllable.
    commands.extend(['label -r YL','label -n AxisTitleY '+label_text(spec['labels']['y'],True),
                     'AxisTitleY.attach=2','AxisTitleY.rotate=90',
                     'AxisTitleY.font=font(%s)'%quote_text(font),'AxisTitleY.fsize='+num(fonts['axis_title_size_pt']),
                     'AxisTitleY.x='+(xat(-.23) if scale=='log10' else 'layer.x.from-.23*(layer.x.to-layer.x.from)'),
                     'AxisTitleY.y=layer.y.from+.5*(layer.y.to-layer.y.from)'])
    if spec.get('y_scale')=='log10':
        yvalues=np.concatenate([column(rows,s[field])+float(s.get('offset',0)) for s in spec['series']
                                for field in ('column','lower','upper') if field in s])
        if np.any(yvalues<=0) or 'y_range' not in spec or min(spec['y_range'])<=0:
            raise ValueError('Log Y requires every plotted value positive and explicit positive y_range')
        if 'y_tick_step' in spec or spec.get('y_ticks') is False:
            raise ValueError('Log Y requires visible decade ticks, not linear y_tick_step')
        lower,upper=map(math.log10,spec['y_range'])
        if not lower.is_integer() or not upper.is_integer() or upper-lower>16:
            raise ValueError('Log Y requires decade endpoints with at most16 decades')
        labels=' '.join('10\\+(%d)'%i for i in range(int(lower),int(upper)+1))
        yat=lambda fraction:'10^(log(layer.y.from)+'+num(fraction)+'*(log(layer.y.to)-log(layer.y.from)))'
        commands.extend(['@TL=0','layer.y.type=2','layer.y.inc=1','layer.y.minorTicks=8',
                         'layer.y.from='+num(spec['y_range'][0]),'layer.y.to='+num(spec['y_range'][1]),
                         'layer.y.label.type=10','layer.y.label.string$="'+labels+'"',
                         'AxisTitleY.y='+yat(.5),'xb.y='+yat(-.23)])
        metadata['y_scale']='log10';metadata['y_range']=spec['y_range']
    if 'y_ticks' in spec:
        metadata['y_ticks'] = spec['y_ticks']
        if not spec['y_ticks']:
            commands.extend(['layer.y.showLabels=0', 'layer.y2.showLabels=0',
                             'layer.y.ticks=0', 'layer.y2.ticks=0'])
    if not native_ready:
        commands=[]
        metadata['native_text_status']='UNAVAILABLE_PERCENT_LABELS;PYTHON_DISPLAY_ONLY'
    return {"id": spec["id"], "graph_id": graph_id, "books": books, "commands": commands, "metadata": metadata}


def ensure_system_fonts():
    global _SYSTEM_FONTS_LOADED
    from matplotlib import font_manager
    if _SYSTEM_FONTS_LOADED:
        return
    windows_fonts = Path('/mnt/c/Windows/Fonts')
    if windows_fonts.is_dir():
        for path in sorted(font_manager.findSystemFonts(fontpaths=[str(windows_fonts)])):
            try:
                font_manager.fontManager.addfont(path)
            except (OSError, RuntimeError):
                continue
    _SYSTEM_FONTS_LOADED = True


def installed_font_names():
    ensure_system_fonts()
    from matplotlib import font_manager
    return sorted({font.name for font in font_manager.fontManager.ttflist})


def plot_text(spec, rows):
    strings = list(spec['labels'].values()) + [spec.get('title','')]
    strings += [s['label'] for s in spec.get('series',[])]
    strings += spec.get('x_tick_labels',[])
    strings += spec.get('y_tick_labels',[])
    groups = spec.get('order',[])
    if spec['kind']=='raincloud' and 'order' not in spec:
        groups = list(dict.fromkeys(row[spec['group']] for row in rows))
    strings += [spec.get('group_labels',{}).get(g,g) for g in groups]
    if any(not isinstance(s,str) for s in strings): raise ValueError('Displayed text must be strings')
    return [math_text(s) for s in strings]


def validate_output_names(plots):
    names = set()
    for plot in plots:
        if plot['id'].casefold().endswith('-reopened'):
            raise ValueError('Plot ID suffix -reopened is reserved for native exports')
        outputs = [plot['id']+s for s in ('.png','.svg','-reopened.png','-layout.json')]
        outputs += [plot['id']+'-'+b['name']+'.csv' for b in plot['books']]
        if plot['metadata']['kind']=='heatmap':outputs.append(plot['id']+'-colorbar.png')
        for name in outputs:
            if name.casefold() in names: raise ValueError('Derived output filename collision: '+name)
            names.add(name.casefold())


def preview_font(spec, rows, style):
    ensure_system_fonts()
    from matplotlib import font_manager
    requested = style["font"]["family"]
    try:
        font_path = font_manager.findfont(font_manager.FontProperties(family=requested), fallback_to_default=False)
    except ValueError as exc:
        raise ValueError('Font "' + requested + '" is not installed. Use --list-fonts and choose --font "Installed name"; no font is downloaded or substituted.') from exc
    font = font_manager.FontProperties(fname=font_path).get_name()
    if font.casefold() != requested.casefold():
        raise ValueError('Choose the actual installed font name: ' + font)
    from matplotlib.ft2font import FT2Font
    charmap = FT2Font(font_path).get_charmap()
    strings = plot_text(spec,rows)
    missing = sorted({c for text in strings for c in text if not c.isspace() and ord(c) not in charmap})
    if missing:
        raise ValueError("Configured preview font lacks these glyphs: " + " ".join(missing) + "; use supported units or explicitly choose a suitable font")
    return font


def layout_legend_handles(legend):
    """Matplotlib 3.6 uses the former spelling; prefer the current API."""
    handles=getattr(legend,'legend_handles',None)
    if handles is None:handles=getattr(legend,'legendHandles',None)
    if handles is None:raise ValueError('Legend handles unavailable')
    return handles


def layout_collection_geometry(collection):
    """Use the paths, drawn size matrices and pixel offsets of a scatter artist."""
    from matplotlib.transforms import Affine2D
    paths=collection.get_paths()
    points=collection.get_offset_transform().transform(np.ma.filled(collection.get_offsets(),np.nan))
    matrices=collection.get_transforms()
    faces,edges=collection.get_facecolors(),collection.get_edgecolors()
    widths=collection.get_linewidths()
    if not paths or not len(points):return
    for i in range(max(len(paths),len(points))):
        x,y=points[i%len(points)]
        if not np.isfinite([x,y]).all():continue  # Masked points are not drawn.
        filled=bool(len(faces) and faces[i%len(faces),3]>0)
        width=float(widths[i%len(widths)]) if len(widths) and len(edges) and edges[i%len(edges),3]>0 else 0.
        if not filled and width<=0:continue
        transform=Affine2D(matrices[i%len(matrices)]) if len(matrices) else Affine2D()
        path=paths[i%len(paths)].transformed(transform+collection.get_transform()+Affine2D().translate(x,y))
        if not np.isfinite(path.vertices).all():raise ValueError('Nonfinite scatter geometry')
        yield path,filled,width


def layout_line_geometry(line):
    """Check visible connecting strokes and Line2D symbols separately."""
    from matplotlib.markers import MarkerStyle
    from matplotlib.transforms import Affine2D
    from matplotlib.colors import to_rgba
    if not line.get_visible() or line.get_alpha()==0:return
    visible=lambda color:to_rgba(color,line.get_alpha())[3]>0
    if line.get_linestyle() not in ('None','none','',' ') and line.get_linewidth()>0 and visible(line.get_color()):
        yield line.get_path().transformed(line.get_transform()),False,line.get_linewidth()
    marker=MarkerStyle(line.get_marker(),fillstyle=line.get_fillstyle())
    if not len(marker.get_path().vertices) or line.get_markersize()<=0:return
    if line.get_markevery() is not None:raise ValueError('Subsampled marker geometry requires a separate check')
    width=line.get_markeredgewidth() if visible(line.get_markeredgecolor()) else 0.
    scale=1. if line.get_marker()==',' else line.get_markersize()*line.figure.dpi/72
    shapes=[(marker.get_path(),marker.get_transform(),line.get_markerfacecolor())]
    if marker.get_alt_path() is not None:
        shapes.append((marker.get_alt_path(),marker.get_alt_transform(),line.get_markerfacecoloralt()))
    for path,transform,color in shapes:
        filled=marker.is_filled() and visible(color)
        if not filled and width<=0:continue
        base=path.transformed(transform+Affine2D().scale(scale))
        for x,y in line.get_transform().transform(line.get_xydata()):
            if np.isfinite([x,y]).all():
                yield base.transformed(Affine2D().translate(x,y)),filled,width


def rendered_layout(fig, ax, dpi):
    """Check export-DPI geometry; this does not replace image inspection."""
    from matplotlib.transforms import Bbox
    from matplotlib.collections import PathCollection
    fig.set_dpi(dpi)
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    canvas=fig.bbox
    text_artists=[]
    for axes in fig.axes:
        text_artists += [axes.xaxis.label,axes.yaxis.label,axes.title]
        text_artists += list(axes.texts)
        # Locator lists include out-of-range ticks which Axis.draw omits.
        for axis in (axes.xaxis,axes.yaxis):
            lower,upper=sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks()+axis.get_minor_ticks():
                if lower<=tick.get_loc()<=upper:
                    text_artists += [tick.label1,tick.label2]
        text_artists += [axes.xaxis.get_offset_text(),axes.yaxis.get_offset_text()]
    legend=ax.get_legend()
    if legend is not None:
        text_artists += legend.get_texts()
    outside=[]
    for text in text_artists:
        if not text.get_visible() or not text.get_text().strip():continue
        box=text.get_window_extent(renderer)
        edges=[name for name,bad in [('left',box.x0<canvas.x0-.5),('right',box.x1>canvas.x1+.5),
                                    ('bottom',box.y0<canvas.y0-.5),('top',box.y1>canvas.y1+.5)] if bad]
        if edges:outside.append({'text':text.get_text(),'edges':edges})
    collisions=[];unchecked=[]
    if legend is not None:
        targets=[]
        for i,text in enumerate(legend.get_texts()):
            targets.append(('text',i,text.get_window_extent(renderer)))
        try:handles=layout_legend_handles(legend)
        except ValueError as error:
            handles=[];unchecked.append({'artist':'legend','reason':str(error)})
        for i,handle in enumerate(handles):
            if not handle.get_visible():continue
            try:
                if isinstance(handle,PathCollection):
                    boxes=[path.get_extents().padded(width*dpi/144)
                           for path,filled,width in layout_collection_geometry(handle)]
                else:
                    width=float(np.max(getattr(handle,'get_linewidth',lambda:1.)()))
                    boxes=[handle.get_window_extent(renderer).padded(max(1.,width*dpi/144))]
                for box in boxes:
                    if not np.isfinite(box.extents).all() or box.x1<box.x0 or box.y1<box.y0:
                        raise ValueError('Invalid legend handle extent')
                    targets.append(('handle',i,box))
            except ValueError as error:
                unchecked.append({'artist':'legend_handle','index':i,'reason':str(error)})
        lines={};collections={}
        for i,line in enumerate(ax.lines):
            try:lines[i]=list(layout_line_geometry(line))
            except ValueError as error:unchecked.append({'artist':'line','index':i,'reason':str(error)})
        for i,collection in enumerate(ax.collections):
            if collection.get_visible() and isinstance(collection,PathCollection):
                try:collections[i]=list(layout_collection_geometry(collection))
                except ValueError as error:unchecked.append({'artist':'collection','index':i,'reason':str(error)})
        def intersects(geometry,box):
            return any(path.intersects_bbox(box.padded(width*dpi/144),filled=filled)
                       for path,filled,width in geometry)
        for kind,index,box in targets:
            # Only the part inside the plotting frame can cover observations.
            box=Bbox.intersection(box,ax.bbox)
            if box is None:continue
            for i,geometry in lines.items():
                if intersects(geometry,box):
                    collisions.append({'data':'line','index':i,'legend':kind,'legend_index':index})
            for i,collection in enumerate(ax.collections):
                if not collection.get_visible():continue
                if isinstance(collection,PathCollection):
                    hit=intersects(collections.get(i,[]),box)
                else:
                    hit=any(path.transformed(collection.get_transform()).intersects_bbox(box,filled=True)
                            for path in collection.get_paths())
                if hit:collisions.append({'data':'collection','index':i,'legend':kind,'legend_index':index})
            for i,shape in enumerate(ax.patches):
                if shape.get_visible() and shape.get_path().transformed(shape.get_transform()).intersects_bbox(box,filled=True):
                    collisions.append({'data':'patch','index':i,'legend':kind,'legend_index':index})
    return {'schema_version':1,'backend':'PYTHON','export_dpi':dpi,
            'status':'NEEDS_REVIEW' if collisions or outside or unchecked else 'NO_GEOMETRIC_ISSUES_DETECTED',
            'legend_collisions':collisions,'text_outside_canvas':outside,
            'geometry_unchecked':unchecked,
            'scope':'Rendered path/marker/fill and text rectangles;not glyph-pixel or native-Origin acceptance',
            'visual_review':'REQUIRED'}


def render(spec, rows, style, target, export_svg=False):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    font = preview_font(spec, rows, style)
    fonts, axes, figure = style["font"], style["axes"], style["figure"]
    matplotlib.rcParams.update({"font.family": font, "font.size": fonts["tick_size_pt"], "svg.fonttype": "none",
                               "axes.labelsize": fonts["axis_title_size_pt"], "axes.titlesize": fonts["title_size_pt"],
                               "legend.fontsize": fonts["legend_size_pt"], "svg.hashsalt": "ai2origin",
                               "axes.linewidth": axes["width_pt"], "axes.edgecolor": axes["color"],
                               "axes.unicode_minus": False,
                               "savefig.facecolor": figure["background_color"],
                               "mathtext.fontset": "custom", "mathtext.rm": font,
                               "mathtext.it": font + ":italic", "mathtext.bf": font + ":bold",
                               "mathtext.cal": font, "mathtext.sf": font, "mathtext.tt": font,
                               "mathtext.fallback": None})
    fig, ax = plt.subplots(figsize=(figure["width_mm"] / 25.4, figure["height_mm"] / 25.4), layout="constrained")
    ax.set_facecolor(figure["background_color"])
    colors = style["colors"]["palette"]
    if spec["kind"] in ("line", "scatter", "line_symbol"):
        for i, series in enumerate(spec["series"]):
            x = column(rows, series.get('x',spec['x']))
            legend_label=display_label(series['label']) if series.get('legend',True) else '_nolegend_'
            appearance = STYLE.series(style, series.get("id", series["column"]), i, series.get("color"))
            offset = float(series.get("offset", 0))
            y, color = column(rows, series["column"]) + offset, appearance["color"]
            if "lower" in series:
                ax.fill_between(x, column(rows, series["lower"]) + offset, column(rows, series["upper"]) + offset, color=color, alpha=0.18)
            series_kind = series.get("kind", spec["kind"])
            if series_kind == "scatter":
                ax.scatter(x, y, color=color, s=appearance["marker_size_pt"]**2, label=legend_label)
            else:
                draw_x,draw_y = pchip_connection(x,y,spec.get('connection_factor',16)) if spec.get('connection')=='pchip' else (x,y)
                ax.plot(draw_x, draw_y, color=color, lw=appearance["width_pt"],
                        ls={"solid":"-", "dash":"--", "dot":":", "dash_dot":"-."}[appearance["line_style"]],
                        marker="o" if series_kind == "line_symbol" and spec.get('connection')!='pchip' else None,
                        ms=appearance["marker_size_pt"], label=legend_label)
                if spec.get('connection')=='pchip':
                    ax.scatter(x,y,color=color,s=appearance['marker_size_pt']**2,zorder=4)
        ax.legend(frameon=False,loc=legend_corner(spec,rows)[0],fontsize=fonts['legend_size_pt'],ncol=spec.get('legend_columns',1))
    elif spec['kind']=='bar':
        x=column(rows,spec['x']);bottom=np.zeros(len(x))
        for i,s in enumerate(spec['series']):
            y=column(rows,s['column']);appearance=STYLE.series(style,s.get('id',s['column']),i,s.get('color'))
            ax.bar(x,y,bottom=bottom,width=.62,color=appearance['color'],edgecolor='none',
                   label=display_label(s['label']) if s.get('legend',True) else '_nolegend_')
            bottom+=y
        ax.set_xticks(x,spec['x_tick_labels']);ax.legend(frameon=False,loc=legend_corner(spec,rows)[0],fontsize=fonts['legend_size_pt'],ncol=spec.get('legend_columns',1))
    elif spec["kind"] == "heatmap":
        xs, ys, grid, _, _ = heatmap_display(rows, spec)
        low, high = map(float, spec["color_range"])
        norm = TwoSlopeNorm(vmin=low, vcenter=float(spec["center"]), vmax=high) if "center" in spec else None
        kwargs = {"norm": norm} if norm else {"vmin": low, "vmax": high}
        image = ax.pcolormesh(xs, ys, grid, shading="nearest", cmap=color_map(spec), rasterized=spec.get('interpolation',{}).get('method')=='bilinear', **kwargs)
        bar=fig.colorbar(image, ax=ax, label=display_label(spec["labels"]["color"]))
        bar.ax.tick_params(labelsize=fonts['annotation_size_pt'])
    else:
        groups = raincloud_geometry(rows, spec)
        vertical = spec.get("orientation", "horizontal") == "vertical"
        full = spec.get("cloud_shape", "half") == "full"
        for g in groups:
            i = g["index"]
            appearance = STYLE.series(style, g["group"], i - 1)
            color = appearance["color"]
            for segment in g['segments']:
                if spec.get('cloud_fill',False):
                    fill=ax.fill_betweenx if vertical else ax.fill_between
                    fill(segment['grid'],segment['bottom'],segment['top'],color=color,alpha=.22,lw=0)
                for contour in ('top','bottom'):
                    if vertical and spec.get('cloud_fill',False):continue
                    if not full and contour=='bottom':continue
                    ax.plot(segment[contour] if vertical else segment['grid'],segment['grid'] if vertical else segment[contour],color=color,lw=.6)
            if spec.get('summary',False):
                ax.bxp([{"med": g["median"], "q1": g["q1"], "q3": g["q3"], "whislo": g["whiskers"][0],
                     "whishi": g["whiskers"][1], "fliers": []}], positions=[i+0.36 if full else i], widths=0.07,
                   vert=vertical, showfliers=False, patch_artist=True,
                   boxprops={"facecolor": "white", "edgecolor": color, "linewidth": 0.6},
                   medianprops={"color": "#222222", "linewidth": 0.9},
                   whiskerprops={"color": color, "linewidth": 0.6}, capprops={"color": color, "linewidth": 0.6})
            ax.scatter(g["jitter_y"] if vertical else g["values"], g["values"] if vertical else g["jitter_y"],
                       s=appearance["marker_size_pt"]**2, color=color, alpha=0.80, edgecolors="none")
        ticks = ax.set_xticks if vertical else ax.set_yticks
        ticks([g["index"] for g in groups], [spec.get("group_labels", {}).get(g["group"], g["group"]) + " (n=" + str(len(g["values"])) + ")" for g in groups])
        (ax.set_xlim if vertical else ax.set_ylim)(0.55, len(groups) + (0.60 if vertical else 0.80))
    ax.set(xlabel=display_label(spec["labels"]["x"]), ylabel=display_label(spec["labels"]["y"]), title=spec.get("title", ""))
    # Both properties express the same edge-to-edge gap in typographic points.
    ax.xaxis.labelpad = ax.yaxis.labelpad = 6
    if spec.get('x_scale')=='log10':
        from matplotlib.ticker import LogLocator,FuncFormatter
        ax.set_xscale('log')
        ax.xaxis.set_major_locator(LogLocator(base=10,numticks=20))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value,pos:r'$10^{%d}$' % round(math.log10(value))))
    if spec.get('y_scale')=='log10':
        from matplotlib.ticker import LogLocator,FuncFormatter
        ax.set_yscale('log')
        ax.yaxis.set_major_locator(LogLocator(base=10,numticks=20))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value,pos:r'$10^{%d}$' % round(math.log10(value))))
    for axis in ("x", "y"):
        if axis + "_range" in spec:
            getattr(ax, "set_" + axis + "lim")(spec[axis + "_range"])
        if axis + "_tick_step" in spec:
            from matplotlib.ticker import MultipleLocator
            getattr(ax, axis + "axis").set_major_locator(MultipleLocator(spec[axis + "_tick_step"]))
    if spec.get("equal_xy"):
        ax.set_aspect("equal", adjustable="box")
    if spec['kind']=='heatmap' and 'y_tick_labels' in spec:
        ax.set_yticks(np.arange(len(spec['y_tick_labels'])),spec['y_tick_labels'])
        ax.set_ylim(-.5,len(spec['y_tick_labels'])-.5)
    ax.spines[["top", "right"]].set_visible(axes["frame"] == "full")
    ax.tick_params(direction=axes["tick_direction"], colors=axes["color"], top=False, right=False)
    if not spec.get('y_ticks', True):
        ax.tick_params(axis='y', which='both', left=False, right=False, labelleft=False, labelright=False)
    ax.grid(axes["major_grid"], alpha=0.2) if axes["major_grid"] else ax.grid(False)
    layout=rendered_layout(fig,ax,style['export']['raster_dpi'])
    layout['plot_id']=spec['id']
    target.with_name(target.name+'-layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if layout['status']=='NEEDS_REVIEW':
        print('LAYOUT '+spec['id']+': '+str(len(layout['legend_collisions']))+' legend intersections, '
              +str(len(layout['text_outside_canvas']))+' text objects outside canvas, '
              +str(len(layout['geometry_unchecked']))+' geometry checks incomplete; adjust task ranges/canvas and inspect exports',file=sys.stderr)
    fig.savefig(target.with_suffix(".png"), dpi=style["export"]["raster_dpi"], metadata={"Software": "Ai2origin synthetic demo" if spec.get("synthetic") else "Ai2origin"})
    if export_svg:
        fig.savefig(target.with_suffix(".svg"), metadata={"Date": None, "Creator": "Ai2origin"})
    plt.close(fig)
    return font


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, nargs='?')
    parser.add_argument("--out", type=Path, help="A new, nonexistent output directory")
    parser.add_argument("--backend", choices=("prepare", "python"), default="prepare")
    parser.add_argument("--svg", action="store_true", help="Also export editable Python SVG when requested; default is PNG only")
    parser.add_argument("--font", help="Exact name of an installed system font; default Arial")
    parser.add_argument("--font-file", type=Path, help="Register an installed local font; never copied into outputs")
    parser.add_argument("--list-fonts", action='store_true', help="List available font names and exit")
    parser.add_argument("--user-style", type=Path, help="User display overrides")
    parser.add_argument("--style", type=Path, help="Task display overrides; highest JSON priority")
    parser.add_argument("--select", nargs='+', metavar='ID', help="Render named recipes only, preserving catalog order")
    args = parser.parse_args(argv)
    if args.list_fonts:
        print(json.dumps(installed_font_names(), ensure_ascii=False))
        return
    if args.config is None or args.out is None:
        parser.error('config and --out are required when plotting')
    if args.font and args.font_file:
        parser.error('Choose --font or --font-file, not both')
    if args.svg and args.backend != "python":
        parser.error("--svg requires --backend python; native SVG is not certified")
    config_path = args.config.resolve()
    identities = {}
    def capture(path):
        path = Path(path).resolve()
        digest = sha256(path)
        if path in identities and identities[path] != digest:
            raise ValueError('Input changed during generation: ' + path.name)
        identities[path] = digest
        return digest
    def verify_inputs():
        for path, digest in identities.items():
            if sha256(path) != digest:
                raise ValueError('Input changed during generation: ' + path.name)
    config_hash = capture(config_path)
    config = load_json(config_path)
    if not isinstance(config,dict) or set(config) - {"schema_version", "style", "style_file", "plots"}:
        raise ValueError("Unsupported project configuration key")
    if type(config.get("schema_version")) is not int or config.get("schema_version") != 1 or not isinstance(config.get("plots"), list) or not config["plots"]:
        raise ValueError("Expected schema_version=1 and a nonempty plots array")
    selected_ids = None
    if args.select:
        available = [p.get('id') if isinstance(p, dict) else None for p in config['plots']]
        if any(not isinstance(v, str) for v in available) or len(set(v.casefold() for v in available)) != len(available):
            raise ValueError('Selection requires unique catalog IDs')
        if len(set(args.select)) != len(args.select) or not set(args.select).issubset(available):
            raise ValueError('Unknown or duplicate selected recipe ID')
        config['plots'] = [p for p in config['plots'] if p['id'] in args.select]
        selected_ids = [p['id'] for p in config['plots']]
    project_style = config_path.parent / config["style_file"] if config.get("style_file") else None
    style_inputs = [('user', args.user_style), ('project-file', project_style), ('task', args.style)]
    for path in [STYLE.DEFAULT_PATH, COLORMAP_PATH] + [p for _, p in style_inputs if p is not None]:
        capture(path)
    style, style_layers = STYLE.resolve(load_json, args.user_style, project_style, config.get("style"), args.style)
    if args.font_file:
        capture(args.font_file)
        from matplotlib import font_manager
        font_manager.fontManager.addfont(str(args.font_file))
        style['font']['family'] = font_manager.FontProperties(fname=str(args.font_file)).get_name()
        style_layers.append('local-font-file')
    if args.font is not None:
        style["font"]["family"] = args.font
        STYLE.validate(style)
        style_layers.append("named-system-font")
    plots, inputs, datasets, ids = [], [], [], set()
    # Complete validation before creating outputs or drawing.
    for index, raw in enumerate(config["plots"], 1):
        if not isinstance(raw,dict):raise ValueError('Each plot must be an object')
        spec = dict(raw)
        if not isinstance(spec.get('id'),str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", spec["id"]) or spec["id"].casefold() in ids:
            raise ValueError("Invalid or duplicate plot ID")
        if re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])', spec['id'], re.I):
            raise ValueError('Plot ID is a reserved Windows device name')
        ids.add(spec["id"].casefold())
        if not isinstance(spec.get('csv'),str) or not spec['csv'].strip():raise ValueError('csv must name a source file')
        source = (config_path.parent / spec["csv"]).resolve()
        source_hash = capture(source)
        rows = read_csv(source)
        plan = prepare_plot(spec, rows, index, style, native_text=args.backend!='python')
        # Derived arithmetic can overflow despite finite raw inputs. Fail before
        # mkdir/CSV writes, including virtual-matrix geometry outside Book.
        for book in plan['books']:
            for row in book['rows']:
                for value in row:
                    if value is not None:num(value)
            # IEEE-754 bytes avoid decimal re-rounding in Windows PowerShell 5.
            # Null padding is encoded as zero here and restored only by its
            # explicit null in rows; a numerical zero remains an observation.
            values = np.array([[0.0 if v is None else v for v in row]
                               for row in book['rows']], dtype='<f8')
            book['data_f64le'] = base64.b64encode(values.tobytes()).decode('ascii')
        plan["metadata"]["source_name"] = source.name
        plan["metadata"]["source_sha256"] = source_hash
        plan["metadata"]["synthetic"] = spec.get("synthetic", False)
        plots.append(plan)
        inputs.append({"name": source.name, "sha256": source_hash, "rows": len(rows)})
        datasets.append((spec, rows))
    validate_output_names(plots)
    if args.backend == "python":
        for spec, rows in datasets:
            preview_font(spec, rows, style)
    verify_inputs()
    if args.out.exists() or args.out.is_symlink():
        raise FileExistsError("Refusing to overwrite an output directory")
    args.out.mkdir(parents=True)
    try:
        plan = {"schema_version": 1, "generator": "Ai2origin 0.3.9", "generator_sha256": sha256(Path(__file__)),
                "config_sha256": config_hash,
                "style": style, "style_layers": style_layers, "style_engine_sha256": sha256(Path(__file__).with_name("style.py")),
                "default_style_sha256":sha256(STYLE.DEFAULT_PATH),
                "colormaps_sha256":sha256(COLORMAP_PATH),
                "style_inputs":[{'layer':name,'file_name':path.name,'sha256':identities[path.resolve()]}
                                for name,path in style_inputs if path is not None],
                "plots": plots, "native_status": "NOT_RUN"}
        if selected_ids is not None:plan['selected_plot_ids'] = selected_ids
        if any(not p['commands'] for p in plots):
            plan['native_plan_status']='UNAVAILABLE_TEXT_ADAPTER;PYTHON_GEOMETRY_ONLY'
        for plot in plots:
            if plot["metadata"]["kind"] == "heatmap":
                from matplotlib.colors import to_rgba
                from matplotlib.image import imsave
                rgba = np.array([to_rgba(c) for c in reversed(plot["metadata"]["colorbar_palette"])])
                pixels = np.repeat(np.repeat(rgba[:, None, :], 16, axis=0), 24, axis=1)
                asset = args.out / (plot["id"] + "-colorbar.png")
                imsave(asset, pixels)
                plot["metadata"]["colorbar_asset"] = {"name": asset.name, "sha256": sha256(asset)}
            for book in plot["books"]:
                with (args.out / (plot["id"] + "-" + book["name"] + ".csv")).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(book["headers"])
                    writer.writerows([["" if v is None else num(v) for v in row] for row in book["rows"]])
        # Assets are generated from the same declared palette, then bound to plan.
        (args.out / "origin-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        actual_fonts = set()
        (args.out / "style.resolved.json").write_text(json.dumps({"style": style, "layers": style_layers}, indent=2) + "\n", encoding="utf-8")
        try:
            if args.backend == "python":
                for spec, rows in datasets:
                    actual_fonts.add(render(spec, rows, style, args.out / spec["id"], export_svg=args.svg))
            verify_inputs()
            status = "PREPARED" if args.backend == "prepare" else "PYTHON_RENDERED"
        except Exception:
            (args.out / "FAILED.txt").write_text("Rendering failed. Partial outputs are not accepted.\n", encoding="utf-8")
            raise
        outputs = [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(args.out.iterdir()) if p.is_file()]
        receipt = {"schema_version": 1, "status": status, "inputs": inputs, "outputs": outputs,
                   "requested_font": style["font"]["family"], "actual_python_fonts": sorted(actual_fonts), "native_origin": "NOT_RUN",
                   "visual_review": "REQUIRED", "scientific_validation": "NOT_CLAIMED"}
        receipt['python_export_formats']=(['png','svg'] if args.svg else ['png']) if args.backend=='python' else []
        if args.backend=='python':
            receipt['python_layout_checks']={p['id']:load_json(args.out/(p['id']+'-layout.json'))['status'] for p in plots}
        import matplotlib
        receipt['environment']={'python':sys.version.split()[0],'numpy':np.__version__,
                                'matplotlib':matplotlib.__version__,'freetype':matplotlib.ft2font.__freetype_version__ if args.backend=='python' else None}
        receipt['font_provenance']=[]
        for family in sorted(actual_fonts):
            from matplotlib import font_manager
            font_path=Path(font_manager.findfont(font_manager.FontProperties(family=family),fallback_to_default=False))
            receipt['font_provenance'].append({'family':family,'file_name':font_path.name,'sha256':sha256(font_path)})
        (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": status, "plots": len(plots), "native_origin": "NOT_RUN", "python_export_formats":receipt['python_export_formats']}))
    except Exception:
        (args.out / "FAILED.txt").write_text("Generation failed; partial outputs are not accepted.\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit('FAIL: ' + str(exc))
