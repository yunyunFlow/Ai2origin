#!/usr/bin/env python3
"""Opt-in analysis contracts; preserve inputs and emit auditable plot recipes."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import importlib.metadata
import inspect
import io
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

VERSION = '0.3.6'
HERE = Path(__file__).resolve().parent
COLORS = ['#B2182B', '#2166AC', '#1B9E77', '#7560A8', '#E4872A', '#737373', '#CC79A7']
UNITS = {'V': ('V', 1.), 'mV': ('V', .001), 'A': ('A', 1.), 'mA': ('A', .001),
         'uA': ('A', 1e-6), 'A/m2': ('A/m2', 1.), 'mA/cm2': ('A/m2', 10.),
         'A/cm2': ('A/m2', 1e4), 's': ('s', 1.), 'ms': ('s', .001),
         'C': ('C', 1.), 'mAh': ('C', 3.6), 'Ah': ('C', 3600.),
         'Hz': ('Hz', 1.), 'kHz': ('Hz', 1000.), 'ohm': ('ohm', 1.),
         'eV': ('eV', 1.), 'cm^-1': ('cm^-1', 1.), 'counts': ('counts', 1.),
         'CPS': ('CPS', 1.), 'a.u.': ('a.u.', 1.), 'absorbance': ('absorbance', 1.)}


def module(name):
    spec = importlib.util.spec_from_file_location('ai2origin_' + name, HERE/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strict_json(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj: raise ValueError('Duplicate JSON key: ' + key)
            obj[key] = value
        return obj
    def bad(value): raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique, parse_constant=bad)


def clean(value):
    if isinstance(value, np.ndarray): return clean(value.tolist())
    if isinstance(value, np.generic): return clean(value.item())
    if isinstance(value, complex): return {'real': clean(value.real), 'imag': clean(value.imag)}
    if isinstance(value, float) and not math.isfinite(value):
        # Fits may return infinite condition numbers, never infinite observations.
        return {'diagnostic': 'NONFINITE_OR_UNBOUNDED', 'value': None}
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    return value


def dump(path, value):
    Path(path).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def keys(obj, allowed, required, name):
    if not isinstance(obj, dict) or set(obj)-set(allowed) or not set(required)<=set(obj):
        raise ValueError(name + ': missing or unsupported fields')


def text(value, name):
    if not isinstance(value, str) or not value.strip(): raise ValueError(name + ': nonempty text required')
    return value


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ': finite real number required')
    if positive and value <= 0: raise ValueError(name + ': positive number required')
    return float(value)


def cell(value, name):
    try:
        dec = Decimal(value)
        result = float(dec)
    except (InvalidOperation, ValueError, OverflowError, TypeError) as exc:
        raise ValueError(name + ': numeric observation required') from exc
    if not math.isfinite(result) or result == 0 and not dec.is_zero():
        raise ValueError(name + ': nonfinite or underflowing observation')
    return result


def csv_bytes(headers, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n'); writer.writerow(headers)
    for row in rows:
        writer.writerow([format(float(v), '.17g') if isinstance(v, (float, np.floating)) else v for v in row])
    return stream.getvalue().encode('utf-8')


class TableCache:
    """One-run immutable lexical tables; hash changes always invalidate use."""
    def __init__(self, reader=None):
        self.reader=reader or module('intake').read_table
        self.tables={};self.sources={}

    def read(self, path, options=None):
        if options is not None and not isinstance(options,dict):raise ValueError('Table options must be an object')
        path=Path(path).resolve();digest=sha(path)
        if path in self.sources and self.sources[path]!=digest:
            raise ValueError('Input changed during analysis')
        self.sources[path]=digest
        key=(digest,path.suffix.lower(),json.dumps(options or {},sort_keys=True,separators=(',',':'),allow_nan=False))
        if key not in self.tables:
            headers,rows,info=self.reader(path,options)
            if sha(path)!=digest:raise ValueError('Input changed while parsing')
            headers=tuple(headers);rows=tuple(tuple(row) for row in rows)
            raw_bytes=csv_bytes(headers,rows)
            self.tables[key]=(headers,rows,tuple(info['source_records']),raw_bytes)
        return digest,self.tables[key]

    def verify(self):
        for path,digest in self.sources.items():
            if sha(path)!=digest:raise ValueError('Input changed during analysis')


class Input:
    def __init__(self, spec, config_dir, job, out, index, cache=None):
        keys(spec, ['file', 'table', 'roles', 'sample_id', 'processing', 'metadata', 'selection'],
             ['file', 'roles', 'sample_id', 'processing'], 'input')
        if text(spec['sample_id'], 'sample_id') != job['sample_id']:
            raise ValueError('Input sample identity differs from the explicitly grouped job')
        text(spec['processing'], 'processing history')
        self.spec = spec; self.path = (config_dir/text(spec['file'], 'input file')).resolve()
        if not self.path.is_file() or self.path.stat().st_size > 64*1024*1024:
            raise ValueError('Missing input or file exceeds the 64 MiB analysis bound')
        self.digest,(headers,rows,source_records,raw_bytes)=(cache or TableCache()).read(self.path,spec.get('table'))
        if not rows or len(rows) > 1_000_000 or len(headers) > 128:
            raise ValueError('Empty/oversized analysis table')
        self.raw_headers, self.raw_rows = headers, rows
        indices = list(range(len(rows)))
        if 'selection' in spec:
            select = spec['selection']; keys(select, ['start', 'stop'], ['start', 'stop'], 'row selection')
            start, stop = select['start'], select['stop']
            if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= len(rows):
                raise ValueError('Selection is an explicit 0-based half-open table-row interval')
            indices = indices[start:stop]
        self.indices = indices; self.values = {}; self.raw_values = {}; self.units = {}; self.original_units = {}
        if not isinstance(spec['roles'], dict) or not spec['roles']: raise ValueError('Explicit column/unit roles required')
        for role, mapping in spec['roles'].items():
            text(role, 'role'); keys(mapping, ['column', 'unit'], ['column', 'unit'], 'role mapping')
            column, unit = text(mapping['column'], 'column'), text(mapping['unit'], 'unit')
            if column not in headers or unit not in UNITS: raise ValueError('Unknown mapped column or unit: ' + column + '/' + unit)
            original = np.array([cell(rows[i][headers.index(column)], column) for i in indices])
            canonical, factor = UNITS[unit]
            with np.errstate(over='ignore', under='ignore'): values = original*factor
            if not np.all(np.isfinite(values)) or np.any((original != 0) & (values == 0)):
                raise ValueError('Unit conversion over/underflow')
            self.raw_values[role], self.values[role] = original, values
            self.units[role], self.original_units[role] = canonical, unit
        self.metadata = spec.get('metadata', {})
        if not isinstance(self.metadata, dict): raise ValueError('Input metadata must be an object')
        raw_name='source-'+hashlib.sha256(raw_bytes).hexdigest()[:16]+'.csv'
        if (out/raw_name).exists():
            if (out/raw_name).read_bytes()!=raw_bytes:raise ValueError('Preserved source-table collision')
        else:(out/raw_name).write_bytes(raw_bytes)
        self.record = {'file_name': self.path.name, 'sha256': self.digest, 'preserved_table': raw_name,
                       'source_table_rows': len(rows), 'selected_table_rows_zero_based': indices,
                       'source_record_indices': [source_records[i] for i in indices],
                       'roles': spec['roles'], 'canonical_units': self.units, 'processing': spec['processing'],
                       'sample_id': spec['sample_id'], 'metadata': self.metadata}

    def get(self, role, unit=None):
        if role not in self.values: raise ValueError('Missing analysis role: ' + role)
        if unit is not None and self.units[role] != unit: raise ValueError('Role '+role+' requires '+unit)
        return self.values[role].copy()


class Figures:
    def __init__(self, out, job): self.out, self.job, self.plots = out, job, []

    def line(self, name, traces, xlabel, ylabel, caption, **options):
        if not traces: return
        counts = {len(t['x']) for t in traces}|{len(t['y']) for t in traces}
        if len(counts) != 1 or min(counts) < 2: raise ValueError('Overlay requires complete equal-length per-series columns')
        columns, values, series = [], [], []
        for i, t in enumerate(traces):
            x, y = np.asarray(t['x'], dtype=float), np.asarray(t['y'], dtype=float)
            if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)): raise ValueError('Nonfinite plot observation')
            xname, yname = 'x'+str(i), 'y'+str(i)
            columns += [xname, yname]; values += [x, y]
            item = {'x': xname, 'column': yname, 'label': t['label'], 'color': t.get('color', COLORS[i%len(COLORS)]),
                    'kind': t.get('kind', 'line')}
            if t.get('legend') is False: item['legend'] = False
            if 'lower' in t:
                item.update(lower='lo'+str(i), upper='hi'+str(i), uncertainty_definition=t['fill_definition'])
                columns += [item['lower'], item['upper']]; values += [t['lower'], t['upper']]
            series.append(item)
        plot_id = self.job['id']+'-'+name; filename = plot_id+'.csv'
        (self.out/filename).write_bytes(csv_bytes(columns, zip(*values)))
        plot = {'id': plot_id, 'kind': 'line', 'csv': filename, 'x': 'x0', 'series': series,
                'labels': {'x': xlabel, 'y': ylabel}, 'synthetic': self.job['synthetic'],
                'caption': caption, 'connect_order': 'acquisition'}
        plot.update(options)
        visible=sum(t.get('legend',True) is not False for t in traces)
        if visible>=4:plot['legend_columns']=2
        # Origin's automatic ticks can crowd narrow frames and three-digit
        # spectral coordinates. Declare readable linear-X majors explicitly.
        if plot.get('equal_xy'):
            span=plot['x_range'][1]-plot['x_range'][0]
            step=nice_tick_step(span)
            plot.setdefault('x_tick_step',step);plot.setdefault('y_tick_step',step)
        elif plot.get('x_scale','linear')=='linear':
            nodes=np.concatenate([np.asarray(t['x']) for t in traces])
            span=float(nodes.max()-nodes.min())
            if span>0:plot.setdefault('x_tick_step',nice_tick_step(span))
        if not plot.get('equal_xy') and plot.get('y_scale','linear')=='linear' and 'y_range' not in plot:
            yy=np.concatenate([np.asarray(t['y']) for t in traces]);lo=float(yy.min());hi=float(yy.max())
            span=hi-lo if hi>lo else max(abs(lo)*.1,1e-12)
            rows=math.ceil(visible/plot.get('legend_columns',1));reserve=min(.7,.10+.11*rows)
            plot['y_range']=[lo-.05*span,hi+span*reserve/(1-reserve)]
            raw_step=(plot['y_range'][1]-plot['y_range'][0])/5
            magnitude=10.**math.floor(math.log10(raw_step))
            plot['y_tick_step']=next(v for v in (1.,2.,2.5,5.,10.) if v>=raw_step/magnitude)*magnitude
        for axis in ('x','y'):
            if plot.get(axis+'_scale')=='log10' and axis+'_range' not in plot:
                nodes=np.concatenate([t[axis] for t in traces]);low=float(nodes.min());high=float(nodes.max())
                if low<=0:raise ValueError('Logarithmic figure requires positive values')
                lo=math.floor(math.log10(low));hi=math.ceil(math.log10(high))
                if low/10.**lo<1.05:lo-=1
                if 10.**hi/high<1.05:hi+=1
                if lo==hi:lo-=1;hi+=1
                plot[axis+'_range']=[10.**lo,10.**hi]
        self.plots.append(plot)

    def map(self, name, x, y, z, xlabel, ylabel, colorlabel, caption, **options):
        plot_id = self.job['id']+'-'+name; filename = plot_id+'.csv'
        (self.out/filename).write_bytes(csv_bytes(['x', 'y', 'z'],
            [(a,b,float(z[j,i])) for j,b in enumerate(y) for i,a in enumerate(x)]))
        lo, hi = float(np.min(z)), float(np.max(z))
        if not lo < hi: raise ValueError('Map needs a nonzero observed intensity range')
        plot = {'id':plot_id,'kind':'heatmap','csv':filename,'x':'x','y':'y','z':'z',
                'labels':{'x':xlabel,'y':ylabel,'color':colorlabel},'synthetic':self.job['synthetic'],
                'caption':caption,'color_range':[lo,hi],'cmap':'redwhiteblue','color_levels':256}
        plot.update(options); self.plots.append(plot)


def trace(x, y, label, color=None, **kwargs):
    return {'x':x, 'y':y, 'label':label, **({'color':color} if color else {}), **kwargs}


def nice_tick_step(span):
    step=number(span,'axis span',True)/5
    if step==0:raise ValueError('Axis tick spacing underflow')
    magnitude=10.**math.floor(math.log10(step))
    if magnitude==0:raise ValueError('Axis tick magnitude underflow')
    result=next(v for v in (1.,2.,2.5,5.,10.) if v>=step/magnitude)*magnitude
    if not math.isfinite(result):raise ValueError('Axis tick spacing overflow')
    return result


def log_bounds(nodes):
    """Enclose actual positive nodes with decade ticks; never resample data."""
    values=np.asarray(nodes,dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values<=0):
        raise ValueError('Logarithmic display requires finite positive nodes')
    low=math.floor(math.log10(float(values.min())))
    high=math.ceil(math.log10(float(values.max())))
    if low==high:high+=1
    try:bounds=[10.**low,10.**high]
    except OverflowError as exc:raise ValueError('Logarithmic display range is unrepresentable') from exc
    if not all(math.isfinite(v) and v>0 for v in bounds) or high-low>16:
        raise ValueError('Logarithmic display needs representable endpoints within16 decades')
    return bounds


def invoke(function, *args, **kwargs):
    try: inspect.signature(function).bind(*args, **kwargs)
    except TypeError as exc: raise ValueError('Missing/unsupported method parameter: '+str(exc)) from exc
    return function(*args, **kwargs)


def cv_groups(inputs, current_basis):
    expected_unit = 'A' if current_basis == 'current_A' else 'A/m2'
    names = list(dict.fromkeys(text(x.metadata.get('branch'), 'CV branch') for x in inputs))
    branches, rates = [], None
    for name in names:
        group = [x for x in inputs if x.metadata['branch']==name]
        selected_rates = [number(x.metadata.get('rate_V_s'), 'rate_V_s', True) for x in group]
        if rates is None: rates = selected_rates
        if selected_rates != rates or len(set(rates)) != len(rates):
            raise ValueError('CV branches need the same ordered distinct rates; no silent sorting/replicate pooling')
        grid = group[0].get('potential', 'V')
        if any(not np.array_equal(x.get('potential', 'V'), grid) for x in group):
            raise ValueError('CV grids differ; explicit validated alignment is required')
        branches.append({'name':name, 'potential_V':grid, 'current_A':np.array([x.get('current', expected_unit) for x in group])})
    return np.array(rates), branches


def cv_dunn(inputs, params, fig):
    cv = module('methods_cv'); opts = dict(params); selected = opts.pop('display_rates_V_s', [])
    rates, branches = cv_groups(inputs, opts.get('current_basis', 'current_A'))
    result = invoke(cv.dunn_contributions, rates, branches, **opts)
    unit = 'mA' if result['current_basis']=='current_A' else 'A m^-2'
    factor=1000. if result['current_basis']=='current_A' else 1.
    loop_e = np.concatenate([b['potential_V'] for b in branches])
    loop_current = np.concatenate([b['current_A'] for b in branches], axis=1)
    caption = 'Source branches concatenated in declared order, including shared endpoint observations. No closure forced. '+result['claim_boundary']
    fig.line('cv', [trace(loop_e, row*factor, f'{rate*1000:g} mV s^-1') for rate,row in zip(rates,loop_current)], 'Potential (V)', 'Current ('+unit+')', caption+' Plot-unit conversion only; SI arrays retained in results.')
    if len(rates)>=2:
        limit=float(np.max(np.abs(loop_current)))*factor
        bb=result['branches']
        paired=len(bb)==2 and np.array_equal(np.asarray(bb[0]['potential_V']),np.asarray(bb[1]['potential_V'])[::-1])
        if paired:
            forward=np.asarray(bb[0]['fit']['current_A'])*factor
            reverse=np.asarray(bb[1]['fit']['current_A'])[:,::-1]*factor
            x=np.asarray(bb[0]['potential_V'])
            if x[0]>x[-1]:x=x[::-1];forward=forward[:,::-1];reverse=reverse[:,::-1]
            # Lower rows reverse rate order; upper rows follow declared rates.
            # Ordinal rows carry explicit positive-rate labels, never negative rates.
            matrix=np.concatenate([reverse[::-1],forward],axis=0)
            labels=[f'R:{r*1000:g}' for r in rates[::-1]]+[f'F:{r*1000:g}' for r in rates]
            fig.map('map',x,np.arange(2*len(rates)),matrix,'Potential (V)',
                    'Branch / scan rate (mV s^-1)','Current ('+unit+')',
                    'Upper block F=first declared sweep; lower block R=return sweep. F potential '+('increases' if bb[0]['potential_V'][0]<bb[0]['potential_V'][-1] else 'decreases')+
                    '. Rows are categorical, labeled with actual positive scan rates. Return coordinates are reversed only for display alignment; acquisition arrays remain untouched. No interpolation across branches or rate categories; shared signed color range centered at zero. '+caption,
                    y_tick_labels=labels,color_range=[-limit,limit],center=0)
        else:
            for bi,b in enumerate(bb):
                fig.map('map-'+str(bi), b['potential_V'], rates*1000, b['fit']['current_A']*factor,
                        'Potential (V)', 'Scan rate (mV s^-1)', 'Current ('+unit+')',
                        'Raw fixed-potential current matrix of one declared branch; actual rate coordinates. Display-only factor-4 bilinear interpolation; common signed color range centered at zero. '+caption,
                        interpolation={'method':'bilinear','factor':4},color_range=[-limit,limit],center=0)
    for rate in selected:
        match = np.flatnonzero(rates==number(rate, 'display rate', True))
        if len(match)!=1: raise ValueError('Display rate must be a supplied scan rate')
        n = int(match[0]); fits = [b['fit'] for b in result['branches']]
        series = [('Observed', loop_current[n], COLORS[5])]
        for label,key,color in [('ν term','linear_component_A',COLORS[0]),('√ν term','sqrt_component_A',COLORS[1]),('Reconstructed','reconstructed_A',COLORS[2])]:
            series.append((label,np.concatenate([b[key][n] for b in fits]),color))
        fig.line('components-'+str(n), [trace(loop_e,y*factor,label,color) for label,y,color in series], 'Potential (V)', 'Current ('+unit+')',
                 'Signed empirical components; no clipping or component sign inversion. '+caption)
        fig.line('residual-'+str(n), [trace(loop_e,np.concatenate([b['residual_A'][n] for b in fits])*factor,'Observed - model')],
                 'Potential (V)', 'Residual ('+unit+')', caption)
    # Exact integrated fractions use actual native stacked columns.
    shares = [r['conditional_model_fractions'] for r in result['aggregate']['per_rate']]
    if all(s is not None for s in shares):
        plot_id=fig.job['id']+'-fractions';filename=plot_id+'.csv'
        (fig.out/filename).write_bytes(csv_bytes(['category','linear','sqrt'],[(i,s['linear']*100,s['sqrt']*100) for i,s in enumerate(shares)]))
        fig.plots.append({'id':plot_id,'kind':'bar','csv':filename,'x':'category','stacked':True,
                          'series':[{'column':'linear','label':'ν term','color':COLORS[0]},{'column':'sqrt','label':'√ν term','color':COLORS[1]}],
                          'x_tick_labels':[f'{rate*1000:g}' for rate in rates], 'labels':{'x':'Scan rate (mV s^-1)','y':'Model fraction (percent)'},
                          'x_range':[-.5,len(rates)-.5],'y_range':[0,135],'legend_columns':2,'synthetic':fig.job['synthetic'],
                          'caption':'100*integral(abs(component) dt)/integral(abs(reconstructed) dt), after residual/opposition QC; actual labelled categories, conditional empirical shares, not identified mechanisms.'})
    return result


def analyze_job(job, inputs, fig):
    method, p = job['method'], dict(job['parameters'])
    if method=='cv_dunn': return cv_dunn(inputs,p,fig)
    if method=='cv_cdl':
        paired=p.pop('paired_cathodic_reversal',False)
        if type(paired) is not bool:raise ValueError('Paired grid reversal must be an explicit boolean')
        rates,branches=cv_groups(inputs,'current_A')
        if len(branches)!=2 or [b['name'] for b in branches]!=['anodic','cathodic']:
            raise ValueError('Cdl requires ordered anodic/cathodic branch identities')
        e=branches[0]['potential_V'];cat_e=branches[1]['potential_V'];cat_i=branches[1]['current_A']
        if paired:
            if not np.array_equal(e,cat_e[::-1]):raise ValueError('Explicit paired reversal does not match actual potential nodes')
            cat_i=cat_i[:,::-1]
        elif not np.array_equal(e,cat_e):raise ValueError('Cdl requires a shared grid or explicit paired reversal')
        result=invoke(module('methods_cv').cdl,rates,e,branches[0]['current_A'],cat_i,**p)
        result['paired_cathodic_working_copy_reversed']=paired
        fig.line('cdl',[trace(rates*1000,np.asarray(result['half_difference_A'])*1000,'(I_a - I_c)/2',kind='scatter'),trace(rates*1000,np.asarray(result['fit']['prediction'])*1000,'OLS')],
                 'Scan rate (mV s^-1)','Half current difference (mA)','Plot converts V/s and A to mV/s and mA only; fit retains SI. Explicit nonfaradaic node/window and condition declarations; conditional apparent capacitance; no automatic ECSA.')
        return result
    if method=='cycle_efficiency':
        if len(inputs)!=2 or [x.metadata.get('branch') for x in inputs]!=['charge','discharge']:
            raise ValueError('Cycle accounting requires explicitly paired charge/discharge branches')
        ch,dis=inputs;result=invoke(module('methods_cv').cycle_efficiency,ch.get('charge','C'),ch.get('potential','V'),dis.get('charge','C'),dis.get('potential','V'),**p)
        fig.line('capacity',[trace(ch.get('charge','C')/3.6,ch.get('potential','V'),'Selected cycle',COLORS[0]),trace(dis.get('charge','C')/3.6,dis.get('potential','V'),'Discharge',COLORS[0],legend=False)],
                 'Branch capacity (mAh)','Cell voltage (V)','Supplied full-cell terminal voltage and branch capacity; pure solid branches, raw nodes retained. CE/EE require complete branch attestation.')
        return result
    if method=='cv_peaks':
        cv=module('methods_cv'); keys(p,['window_V','polarity','solution_diffusion'],['window_V','polarity'],'peak parameters')
        peaks=[cv.peak_window(x.get('potential','V'),x.get('current','A'),p['window_V'],p['polarity']) for x in inputs]
        rates=[number(x.metadata.get('rate_V_s'),'rate_V_s',True) for x in inputs]
        if len(set(rates))!=len(rates): raise ValueError('Duplicate rates need an explicit replicate contract')
        result={'peaks':peaks,'rates_V_s':rates,'status':'HOLD_PEAK_WINDOW' if any(x['status']!='ok' for x in peaks) else 'DESCRIPTIVE_PEAK_FITS'}
        if result['status']=='DESCRIPTIVE_PEAK_FITS':
            fit=cv.scan_rate_fit(rates,[x['current_A'] for x in peaks]);result['fit']=fit
            fig.line('sqrt-rate',[trace(np.sqrt(rates),fit['peak_magnitude_A'],'Raw peaks',kind='scatter'),trace(np.sqrt(rates),fit['sqrt_fit']['prediction'],'OLS')],
                     '√ν (V^0.5 s^-0.5)','|Peak current| (A)','Descriptive peak-magnitude fit with free intercept; no solid-electrode diffusivity inference.')
            fig.line('b-value',[trace(np.log10(rates),np.log10(fit['peak_magnitude_A']),'Raw peaks',kind='scatter'),trace(np.log10(rates),fit['log_fit']['prediction']/math.log(10),'OLS')],
                     'log10[ν/(V s^-1)]','log10[|I_p|/A]','Descriptive b exponent; logarithms use explicit reference units.')
            if 'solution_diffusion' in p:
                result['solution_diffusion']=invoke(cv.randles_sevcik_diffusivity,fit['sqrt_slope_A_per_sqrt_V_s'],**p['solution_diffusion'])
        return result
    if method=='gitt':
        spectra=module('methods_spectra'); results=[];axis=p.pop('coordinate_axis',None)
        keys(axis,['label','unit'],['label','unit'],'GITT coordinate axis')
        for i,x in enumerate(inputs):
            args={**p,**x.metadata}; declarations=args.pop('physical_conditions',{})
            keys(declarations,['small_perturbation','diffusion_dominance','effective_geometry_verified'],[],'GITT physical conditions')
            if any(type(v) is not bool and v is not None for v in declarations.values()):
                raise ValueError('GITT physical conditions must be explicit booleans or null')
            tolerance=args.pop('current_constancy_tolerance',None)
            for field in ['pulse_id','coordinate','coordinate_unit']:args.pop(field,None)
            current=x.get('current','A');mean=float(np.mean(current))
            if tolerance is None: raise ValueError('Declare current_constancy_tolerance')
            tol=number(tolerance,'current constancy tolerance')
            if not 0<=tol<1: raise ValueError('Current constancy tolerance must be [0,1)')
            result=invoke(spectra.gitt_pulse,x.get('time','s'),x.get('potential','V'),**args)
            reasons=list(result['hold_reasons'])
            if mean==0 or np.max(np.abs(current-mean))>tol*abs(mean):reasons.append('CURRENT_NOT_CONSTANT_NONZERO')
            for condition in ['small_perturbation','diffusion_dominance','effective_geometry_verified']:
                if declarations.get(condition) is not True:reasons.append('NOT_ESTABLISHED:'+condition)
            result.update(hold_reasons=reasons,physical_conditions=declarations,mean_current_A=mean,current_constancy_tolerance=tol)
            if reasons:result.update(status='HOLD',D_conditional_m2_s=None)
            coordinate=number(x.metadata.get('coordinate'),'GITT coordinate');result['coordinate']=coordinate
            if x.metadata.get('coordinate_unit')!=axis['unit']:raise ValueError('GITT coordinate-unit mismatch')
            result['pulse_id']=text(x.metadata.get('pulse_id'),'pulse identity');results.append(result)
            indices=result['fit_source_indices_zero_based'];t=x.get('time','s');e=x.get('potential','V')
            fig.line('pulse-'+str(i),[trace(t,e,'Recorded pulse')],'Time (s)','Potential (V)','Every recorded pulse node; no iR subtraction or smoothing.')
            origin=float(e[indices[0]])
            fig.line('window-'+str(i),[trace(np.sqrt(t[indices]),(e[indices]-origin)*1000,'Selected observations',kind='scatter'),trace(np.sqrt(t[indices]),(np.asarray(result['fit_E_V'])-origin)*1000,'OLS')],
                     '√t (s^0.5)','E - E_first selected (mV)','Display subtracts the first selected potential and converts V to mV. E vs sqrt(t) slope fit uses original V; intercept excluded from delta E_tau; all raw nodes retained separately.')
        accepted=[r for r in results if r['D_conditional_m2_s'] is not None]
        if len(accepted)>=2:
            fig.line('diffusivity',[trace([r['coordinate'] for r in accepted],[r['D_conditional_m2_s'] for r in accepted],'Conditional D',kind='line_symbol')],
                     axis['label']+' ('+('percent' if axis['unit']=='%' else axis['unit'])+')','D (m^2 s^-1)','Only explicitly accepted short-time model diagnostics shown; held pulse IDs and all candidates remain in results.json.',y_scale='log10')
        return {'status':'HOLD' if len(accepted)!=len(results) else 'CONDITIONAL_MODEL_RESULTS','pulses':results,
                'plotted_pulse_ids':[r['pulse_id'] for r in accepted],'held_pulse_ids':[r['pulse_id'] for r in results if r not in accepted]}
    if method=='ica':
        if len(inputs)!=1: raise ValueError('ICA selects one explicit monotonic branch')
        x=inputs[0];result=invoke(module('methods_cv').ica,x.get('potential','V'),x.get('charge','C'),**p)
        fig.line('ica',[trace(result['V_center_V'],result['dQ_dV_C_per_V']/3.6,'Finite-volume ICA')],'Potential (V)','dQ/dV (mAh V^-1)',
                 'Adjacent-node finite-volume derivative; signed supplied capacity convention, no smoothing. Integral closes to original capacity change.')
        fig.line('dva',[trace(result['Q_center_C']/3.6,result['dV_dQ_V_per_C']*3.6,'Finite-volume DVA')],'Capacity (mAh)','dV/dQ (V mAh^-1)',
                 'Reciprocal interval derivative; repeats/turns refused, no averaging or deleted observations.')
        return {'status':'FINITE_VOLUME_ACCOUNTING',**result}
    if method=='tafel':
        if len(inputs)!=1: raise ValueError('Tafel selects one signed LSV branch')
        keys(p,['prepare','fit'],['prepare','fit'],'Tafel parameters');x=inputs[0];m=module('methods_tafel')
        if x.original_units['current'] not in m.UNITS: raise ValueError('Tafel current unit is explicitly A/mA/A/cm2/mA/cm2')
        prepare=dict(p['prepare']);prepare['current_unit']=x.original_units['current']
        data=invoke(m.prepare_lsv,x.get('potential','V'),x.raw_values['current'],**prepare)
        fit=invoke(m.fit_tafel,data,**p['fit'])
        displayed_unit={'A/cm2':'A cm^-2','mA/cm2':'mA cm^-2'}.get(data['raw_current_unit'],data['raw_current_unit'])
        fig.line('lsv',[trace(data['raw_E_V'],data['raw_current'],'Recorded LSV')],'Supplied potential (V)','Current ('+displayed_unit+')','Raw supplied reference/current units and every node retained.')
        if fit.get('log10_abs_current_over_reference') is not None:
            xx=fit['log10_abs_current_over_reference'];fig.line('tafel',[trace(xx,fit['eta_V'],'Selected observations',kind='scatter'),trace(xx,fit['fit_eta_V'],'OLS')],
                'log10[|'+('j' if '/cm2' in fit['log_reference_unit'] else 'I')+'| / ('+str(fit['log_reference_value'])+' '+fit['log_reference_unit'].replace('/cm2',' cm^-2')+')]','Overpotential (V)','Apparent selected-window Tafel slope; '+fit['claim'])
        return {'status':fit['status'],'prepared':data,'fit':fit}
    if method in ['eis_rc','drt']:
        m=module('methods_impedance');results=[]
        residual_limit=number(p.pop('model_residual_limit',.05),'model relative complex residual limit',True)
        if residual_limit>=1:raise ValueError('Model residual limit must be in (0,1)')
        selected=p.pop('selected_lambda',None);axis=p.pop('condition_axis',None)
        for i,x in enumerate(inputs):
            f=x.get('frequency','Hz');zr=x.get('real','ohm');zi=x.get('imaginary','ohm')
            convention=x.metadata.get('imaginary_convention')
            if convention not in ['Zimag','minus_Zimag']: raise ValueError('Declare mathematical or negated imaginary convention')
            z=zr+1j*(zi if convention=='Zimag' else -zi)
            result=invoke(m.fit_rc if method=='eis_rc' else m.drt_tikhonov,f,z,**p);results.append(result)
            fit=result['Z_fit'] if method=='eis_rc' else next((s['Z_fit'] for s in result['solutions'] if s['lambda']==selected),None)
            if fit is None:raise ValueError('Select a displayed lambda explicitly from the computed sensitivity list')
            displayed=result if method=='eis_rc' else next(s for s in result['solutions'] if s['lambda']==selected)
            result['displayed_fit_quality']={'relative_complex_rmse':displayed['relative_complex_rmse'],'declared_limit':residual_limit,
                'status':'CONDITIONAL_MODEL_RESIDUAL' if displayed['relative_complex_rmse']<=residual_limit else 'HOLD_MODEL_RESIDUAL'}
            all_values=np.r_[zr,-z.imag,fit.real,-fit.imag];low=min(0.,float(all_values.min()));high=max(0.,float(all_values.max()));span=high-low
            if span<=0:raise ValueError('Nyquist needs nonzero physical range')
            bounds=[low-span*.05,high+span*.08]
            fig.line('nyquist-'+str(i),[trace(zr,-z.imag,'Recorded',kind='scatter'),trace(fit.real,-fit.imag,'Model')],
                     'Re(Z) (Ω)','-Im(Z) (Ω)','Equal physical axes; model elements/relaxations unassigned; KK validation not performed.',equal_xy=True,x_range=bounds,y_range=bounds)
            fig.line('residual-'+str(i),[trace(f,(fit-z).real,'Real residual'),trace(f,(fit-z).imag,'Imaginary residual')],
                     'Frequency (Hz)','Model - recorded (Ω)','Signed residuals of every supplied frequency; no point removal.',x_scale='log10',x_range=log_bounds(f))
            if method=='drt':
                tau=result['tau_s'];fig.line('drt-'+str(i),[trace(tau,s['gamma_ohm'],f"λ = {s['lambda']:g}") for s in result['solutions']],
                     'Relaxation time, τ (s)','γ(ln τ) (Ω)','Nonnegative RC-kernel DRT per natural-log time; all explicitly supplied lambdas retained; no automatic selection or chemical assignment.',x_scale='log10',x_range=log_bounds(tau))
        if method=='drt' and len(inputs)>=2:
            keys(axis,['label','unit','values'],['label','unit','values'],'condition axis')
            yy=np.array([number(v,'condition coordinate') for v in axis['values']])
            if len(yy)!=len(inputs) or len(np.unique(yy))!=len(yy):raise ValueError('Distinct declared condition values must match inputs')
            z=np.array([next(s['gamma_ohm'] for s in r['solutions'] if s['lambda']==selected) for r in results]);tau=results[0]['tau_s']
            fig.map('map',tau,yy,z,'Relaxation time, τ (s)',axis['label']+' ('+axis['unit']+')','γ(ln τ) (Ω)',
                    'Same kernel/grid/weighting/lambda across supplied conditions. Display-only factor-8 bilinear interpolation in log10(tau), condition; raw nodes unchanged. White is the intensity-range midpoint.',
                    x_scale='log10',x_range=log_bounds(tau),interpolation={'method':'bilinear','factor':8},color_range=[0.,float(np.max(z))])
        return {'status':'HOLD_MODEL_RESIDUAL' if any(r['displayed_fit_quality']['status']=='HOLD_MODEL_RESIDUAL' for r in results) else 'MODEL_DIAGNOSTICS_KK_UNVERIFIED','inputs':results,'selected_display_lambda':selected}
    if method in ['spectra_peaks','spectra_doublet']:
        if len(inputs)!=1:raise ValueError('Select one explicitly processed spectral region')
        x=inputs[0];profile=p.pop('profile',None);m=module('methods_spectra')
        energy_options=p.pop('energy',None)
        expected='eV' if profile=='xps' else 'cm^-1' if profile in ['raman','ftir'] else None
        if expected is None:raise ValueError('Declare raman, ftir or xps profile')
        xx=x.get('coordinate',expected);yy=x.get('intensity')
        if profile=='xps':
            if x.metadata.get('energy_type') not in ['binding','kinetic'] or x.metadata.get('scan_type')!='high_resolution' or x.units['intensity'] not in ['counts','CPS']:
                raise ValueError('XPS fit needs explicit energy type, high_resolution and counts/CPS')
            state=x.metadata.get('background_state')
            if state not in ['none','subtracted','unknown']:raise ValueError('Declare XPS background_state none/subtracted/unknown')
            if state=='subtracted' and p.get('baseline',{}).get('kind')!='none':raise ValueError('Refusing double background processing')
            if x.metadata['energy_type']=='kinetic' or energy_options is not None:
                energy_result=invoke(m.xps_energy,xx,energy_type=x.metadata['energy_type'],**(energy_options or {}));xx=np.array(energy_result['binding_energy_eV'])
            else:energy_result=None
            text(x.metadata.get('energy_calibration'),'XPS energy calibration history')
        elif energy_options is not None:raise ValueError('XPS energy conversion cannot be applied to Raman/FTIR')
        if profile=='ftir' and x.units['intensity']!='absorbance':raise ValueError('FTIR peaks require explicit absorbance; no implicit transmittance conversion')
        background_result=None
        if p.get('baseline',{}).get('kind')=='shirley':
            if profile!='xps':raise ValueError('Shirley is an explicit binding-energy XPS background')
            bg=dict(p['baseline']);bg.pop('kind');background_result=invoke(m.shirley_background,xx,yy,**bg)
            if background_result['status']!='CONDITIONAL_SHIRLEY':raise ValueError('Shirley failed to converge; no peak fit accepted')
            fixed=background_result['background_source_order']
            if p.get('reverse_working_copy') is True and np.all(np.diff(xx)<0):fixed=fixed[::-1]
            p['baseline']={'kind':'supplied','values':fixed,'source':'Explicit iterative Shirley; endpoints and convergence retained in results'}
        result=invoke(m.fit_doublet if method=='spectra_doublet' else m.fit_peaks,xx,yy,**p)
        if profile=='xps':
            result['energy_transform']=energy_result;result['background_algorithm']=background_result
            if state=='unknown':
                result['hold_reasons'].append('UNKNOWN_PREVIOUS_BACKGROUND');result.update(status='HOLD_MODEL',accepted_numeric_fit=False)
        traces=[trace(result['x_working'],result['y_working'],'Observed',COLORS[5]),trace(result['x_working'],result['fit'],'Total model',COLORS[0]),trace(result['x_working'],result['baseline'],'Declared baseline',COLORS[4])]
        traces += [trace(result['x_working'],component,'Component '+str(i+1),COLORS[(i+1)%len(COLORS)]) for i,component in enumerate(result['components'])]
        label='Binding energy (eV)' if profile=='xps' else 'Raman shift (cm^-1)' if profile=='raman' else 'Wavenumber (cm^-1)'
        fig.line('fit',traces,label,'Intensity ('+x.units['intensity']+')','Explicit spectral region/model/centers/width bounds/background; no chemical identity or area-to-population assignment. '+result['claim'])
        fig.line('residual',[trace(result['x_working'],result['residual'],'Observed - model')],label,'Residual ('+x.units['intensity']+')',result['claim'])
        return result
    if method=='cv_correct':
        if len(inputs)!=1:raise ValueError('Correct one explicitly identified branch at a time')
        keys(p,['ir','tail','background','alignment'],[],'CV correction');x=inputs[0];m=module('methods_cv_corrected');e=x.get('potential','V');i=x.get('current','A');results={}
        corrected_e=e.copy();corrected_i=i.copy()
        if 'ir' in p:
            results['ir']=invoke(m.ir_correct,e,i,**p['ir']);corrected_e=results['ir']['corrected_potential_V']
        if 'tail' in p:
            args=dict(p['tail']);args['current_unit']='A'
            results['tail']=invoke(m.fit_exponential_tail,corrected_e,i,**args);corrected_i=i-results['tail']['tail']
        if 'background' in p:
            keys(p['background'],['role','source'],['role','source'],'independent background')
            text(p['background']['source'],'background provenance');background=x.get(p['background']['role'],'A')
            corrected_i=corrected_i-background;results['background']={'values_A':background,'source':p['background']['source']}
        if not p:raise ValueError('No processing operation declared')
        fig.line('raw',[trace(e,i,'Recorded')],'Supplied potential (V)','Current (A)','Every original node/order retained before explicit processing.')
        fig.line('corrected',[trace(corrected_e,corrected_i,'Explicit corrected branch')],'Corrected potential (V)','Current (A)','Declared signed iR/tail/background operations only; no inferred resistance or capacitance. Folds retained.')
        if 'alignment' in p:
            args=dict(p['alignment']);args['current_unit']='A';results['alignment']=invoke(m.resample_branch,corrected_e,corrected_i,**args)
        holds=[key for key,value in results.items() if isinstance(value,dict) and str(value.get('status','')).startswith('HOLD')]
        return {'status':'HOLD_PROCESSING_MODEL' if holds else 'CONDITIONAL_EXPLICIT_PROCESSING','hold_operations':holds,'raw_potential_V':e,'raw_current_A':i,'corrected_potential_V':corrected_e,'corrected_current_A':corrected_i,'operations':results}
    raise ValueError('Unsupported analysis method: '+str(method))


def run(config_path, out):
    config_path=Path(config_path).resolve();out=Path(out).resolve();config_digest=sha(config_path);config=strict_json(config_path)
    keys(config,['schema_version','jobs'],['schema_version','jobs'],'analysis config')
    if config['schema_version']!=1 or type(config['schema_version']) is not int:raise ValueError('Analysis schema_version must be1')
    if not isinstance(config['jobs'],list) or not 1<=len(config['jobs'])<=32:raise ValueError('Supply1..32 explicit analysis jobs')
    if out.exists():raise ValueError('Use a new output directory; no overwrite')
    ids=[]
    for job in config['jobs']:
        keys(job,['id','method','sample_id','inputs','parameters','synthetic'],['id','method','sample_id','inputs','parameters','synthetic'],'job')
        identifier=text(job['id'],'job ID')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}',identifier) or identifier.casefold() in ['con','prn','aux','nul']:
            raise ValueError('Unsafe job ID')
        ids.append(identifier.casefold());text(job['method'],'method');text(job['sample_id'],'sample_id')
        if type(job['synthetic']) is not bool or not isinstance(job['parameters'],dict) or not isinstance(job['inputs'],list) or not 1<=len(job['inputs'])<=32:
            raise ValueError('Explicit synthetic flag, parameter object and1..32 inputs required')
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate case-insensitive job ID')
    out.mkdir(parents=True);reports=[];plots=[];cache=TableCache()
    try:
        for job in config['jobs']:
            inputs=[Input(s,config_path.parent,job,out,i,cache) for i,s in enumerate(job['inputs'])]
            figures=Figures(out,job);result=analyze_job(job,inputs,figures);plots+=figures.plots
            reports.append({'id':job['id'],'method':job['method'],'sample_id':job['sample_id'],'parameters':job['parameters'],
                            'inputs':[x.record for x in inputs],'result':result,'plots':[p['id'] for p in figures.plots],
                            'scientific_validation':'NOT_ESTABLISHED_FOR_REAL_MATERIAL'})
        cache.verify()
        if sha(config_path)!=config_digest:raise ValueError('Config changed during analysis')
        dump(out/'results.json',{'schema_version':1,'version':VERSION,'jobs':reports})
        if plots:dump(out/'plot.json',{'schema_version':1,'style':{'figure':{'width_mm':110,'height_mm':80},'font':{'legend_size_pt':8}},'plots':plots})
        outputs=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.iterdir()) if p.is_file()]
        versions={'python':'.'.join(map(str,sys.version_info[:3])),'numpy':np.__version__}
        try:versions['scipy']=importlib.metadata.version('scipy')
        except importlib.metadata.PackageNotFoundError:versions['scipy']=None
        dump(out/'analysis-receipt.json',{'schema_version':1,'version':VERSION,'status':'ANALYSIS_COMPLETE',
             'analysis_script_sha256':sha(__file__),'method_module_sha256':{p.name:sha(p) for p in sorted(HERE.glob('methods_*.py'))},
             'table_parser_sha256':sha(HERE/'intake.py'),'config_sha256':config_digest,'outputs':outputs,'job_count':len(reports),'plot_count':len(plots),
             'installed_dependency_versions':versions,
             'visual_review':'REQUIRED','native_origin':'NOT_RUN','scientific_validation':'NOT_ESTABLISHED'})
    except Exception as exc:
        (out/'FAILED.txt').write_text('Analysis incomplete: '+str(exc)+'\n',encoding='utf-8')
        raise
    return {'status':'ANALYSIS_COMPLETE','jobs':len(reports),'plots':len(plots),'native_origin':'NOT_RUN'}


def verify(folder, repeat=None, config=None):
    folder=Path(folder);receipt=strict_json(folder/'analysis-receipt.json')
    if (folder/'FAILED.txt').exists() or receipt['status']!='ANALYSIS_COMPLETE':raise ValueError('Failed analysis generation')
    names=set()
    for entry in receipt['outputs']:
        name=entry['name'];path=folder/name
        if not isinstance(name,str) or not name or Path(name).name!=name or any(c in name for c in ['/', '\\', ':']) or name.casefold() in names:
            raise ValueError('Unsafe/duplicate analysis output name')
        names.add(name.casefold())
        if not path.is_file() or path.is_symlink() or path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:
            raise ValueError('Analysis output hash/size changed')
    if not names:raise ValueError('Empty analysis inventory')
    exact_names={e['name'] for e in receipt['outputs']}|{'analysis-receipt.json'}
    for path in folder.iterdir():
        if not path.is_file() or path.is_symlink() or path.name not in exact_names:
            raise ValueError('Unlisted analysis entry')
    if config is not None:
        config=Path(config).resolve()
        if sha(config)!=receipt['config_sha256']:raise ValueError('Analysis config changed')
        cfg=strict_json(config);reports=strict_json(folder/'results.json')['jobs']
        if len(cfg['jobs'])!=len(reports):raise ValueError('Analysis job inventory changed')
        for job,report in zip(cfg['jobs'],reports):
            if any(job[k]!=report[k] for k in ['id','method','sample_id','parameters']) or len(job['inputs'])!=len(report['inputs']):
                raise ValueError('Analysis job/input identity changed')
            for spec,record in zip(job['inputs'],report['inputs']):
                if sha(config.parent/spec['file'])!=record['sha256']:raise ValueError('Original analysis source changed')
    if repeat is not None:
        other=verify(repeat,config=config)
        comparison=strict_json(Path(repeat)/'analysis-receipt.json')
        if receipt!=comparison:raise ValueError('Repeated analysis receipt differs')
        for entry in receipt['outputs']:
            if (folder/entry['name']).read_bytes()!=(Path(repeat)/entry['name']).read_bytes():raise ValueError('Repeated analysis output differs')
    return {'status':'PASS','files_verified':len(names),'repeat':'BYTE_IDENTICAL' if repeat else None,'scientific_validation':'NOT_ESTABLISHED'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('config',nargs='?');parser.add_argument('--out')
    parser.add_argument('--check');parser.add_argument('--repeat');args=parser.parse_args()
    try:
        if args.check:
            if args.out:raise ValueError('--check is read-only and does not accept --out')
            result=verify(args.check,args.repeat,args.config)
        else:
            if not args.config or not args.out or args.repeat:raise ValueError('Supply config and --out, or --check with optional --repeat')
            result=run(args.config,args.out)
        print(json.dumps(result));exit_code=0
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        print('FAIL: '+str(exc),file=sys.stderr);exit_code=1
    return exit_code


if __name__=='__main__':raise SystemExit(main())
