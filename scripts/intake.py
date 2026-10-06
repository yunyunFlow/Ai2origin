#!/usr/bin/env python3
"""Strict, read-only-source flat-table intake; no implicit scientific processing."""
import argparse
import csv
import hashlib
import io
import importlib.util
import json
import math
from decimal import Decimal, InvalidOperation
from statistics import mean
from pathlib import Path, PurePosixPath
import re
import zipfile
from xml.etree import ElementTree as ET

VERSION = '0.3.5'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate mapping key: ' + key)
            result[key] = value
        return result
    def bad(value): raise ValueError('Non-finite mapping constant: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique, parse_constant=bad)


def keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError('Unsupported ' + label + ' keys')


def xlsx_rows(path, sheet=None):
    """Read stored OOXML values, retaining absent cells. Never evaluate formulas."""
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len({i.filename for i in members}) != len(members):
            raise ValueError('Duplicate Excel ZIP members')
        if sum(i.file_size for i in members) > 128 * 1024 * 1024:
            raise ValueError('Excel workbook exceeds the bounded flat-table reader')
        if any(i.flag_bits & 1 for i in members):
            raise ValueError('Encrypted Excel workbook is unsupported')
        if any('externalLinks/' in i.filename or i.filename.endswith('vbaProject.bin') for i in members):
            raise ValueError('External links/macros are unsupported')
        wb = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = wb.findall('s:sheets/s:sheet', NS)
        if sheet is None and len(sheets) != 1:
            raise ValueError('Select an exact Excel sheet; no automatic multi-sheet merge')
        chosen = [s for s in sheets if sheet is None or s.get('name') == sheet]
        if len(chosen) != 1 or chosen[0].get('state', 'visible') != 'visible':
            raise ValueError('Missing, ambiguous or hidden Excel sheet')
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        relation = [n for n in rels if n.get('Id') == chosen[0].get('{' + REL + '}id')]
        if len(relation) != 1 or relation[0].get('TargetMode') == 'External':
            raise ValueError('Unsafe Excel worksheet relationship')
        target = relation[0].get('Target', '')
        if '\\' in target or '..' in PurePosixPath(target).parts:
            raise ValueError('Unsafe Excel worksheet path')
        target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        ws = ET.fromstring(archive.read(target))
        if ws.find('s:mergeCells', NS) is not None:
            raise ValueError('Merged Excel report requires a dedicated parser/fixture')
        if any(n.get('hidden') in ('1', 'true') for n in ws.findall('s:cols/s:col', NS)):
            raise ValueError('Hidden Excel columns require explicit handling')
        shared = []
        styles = []
        if 'xl/styles.xml' in archive.namelist():
            style_root = ET.fromstring(archive.read('xl/styles.xml'))
            formats = {int(n.get('numFmtId')):n.get('formatCode','') for n in style_root.findall('s:numFmts/s:numFmt',NS)}
            if len(formats) != len(style_root.findall('s:numFmts/s:numFmt',NS)):
                raise ValueError('Duplicate Excel number-format definitions')
            for xf in style_root.findall('s:cellXfs/s:xf',NS):
                identifier = int(xf.get('numFmtId','0'))
                if identifier in formats:
                    # Literals, escapes, colors, conditions and locale codes
                    # do not create date tokens. Elapsed-time brackets do.
                    code = re.sub(r'"[^\"]*"|\\.|_.|\*.', '', formats[identifier])
                    elapsed = bool(re.search(r'\[[hms]+\]',code,re.I))
                    code = re.sub(r'\[[^\]]*\]','',code)
                    temporal = elapsed or bool(re.search(r'[ymdhs]',code,re.I))
                elif identifier in set(range(14,23)) | set(range(27,37)) | {45,46,47} | set(range(50,59)):
                    temporal = True
                elif identifier in set(range(0,14)) | set(range(37,45)) | {48,49}:
                    temporal = False
                else:
                    raise ValueError('Unknown Excel number-format semantics require explicit handling')
                styles.append(temporal)
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            shared = [''.join(t.text or '' for t in n.findall('.//s:t', NS)) for n in strings.findall('s:si', NS)]
        rows, indices = [], []
        for row in ws.findall('s:sheetData/s:row', NS):
            if row.get('hidden') in ('1', 'true'):
                raise ValueError('Hidden Excel rows require explicit handling')
            row_index = int(row.get('r', '0'))
            if not 1 <= row_index <= 1000000 or indices and row_index <= indices[-1]:
                raise ValueError('Invalid Excel row order')
            if row_index != (indices[-1] + 1 if indices else 1):
                raise ValueError('Absent Excel rows require explicit handling; refusing silent row deletion')
            values = {}
            for cell in row.findall('s:c', NS):
                address = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', cell.get('r', ''))
                if not address or int(address[2]) != row_index:
                    raise ValueError('Invalid Excel cell address')
                col = 0
                for char in address[1]:
                    col = 26 * col + ord(char) - 64
                if col > 16384 or col in values:
                    raise ValueError('Invalid or duplicate Excel cell')
                if cell.find('s:f', NS) is not None:
                    raise ValueError('Excel formulas/cached results require author-supplied values')
                kind = cell.get('t', 'n')
                value = cell.findtext('s:v', '', NS)
                if kind=='n' and value and (styles or 's' in cell.attrib):
                    style_index = int(cell.get('s','0'))
                    if not 0 <= style_index < len(styles):raise ValueError('Invalid Excel cell style index')
                    if styles[style_index]:raise ValueError('Excel date/time serial requires explicit handling; refusing numeric reinterpretation')
                if kind == 's':
                    try:
                        index = int(value)
                        if not 0 <= index < len(shared):
                            raise ValueError('Shared string index out of range')
                        value = shared[index]
                    except (ValueError, IndexError) as exc:
                        raise ValueError('Invalid Excel shared string') from exc
                elif kind == 'inlineStr':
                    value = ''.join(n.text or '' for n in cell.findall('.//s:t', NS))
                elif kind not in ('n', 'str'):
                    raise ValueError('Excel date/error cell requires explicit handling')
                values[col] = value
            rows.append([values.get(i, '') for i in range(1, max(values, default=0) + 1)])
            indices.append(row_index)
        return rows, indices, chosen[0].get('name')


def read_table(path, options=None):
    options = {} if options is None else options
    keys(options, ['delimiter', 'encoding', 'skip_rows', 'header', 'names', 'sheet'], 'table')
    skip = options.get('skip_rows', 0)
    header = options.get('header', True)
    if type(skip) is not int or skip < 0 or type(header) is not bool:
        raise ValueError('Invalid explicit header/skip_rows')
    suffix = Path(path).suffix.lower()
    if suffix == '.xlsx':
        if set(options) & {'delimiter', 'encoding'}:
            raise ValueError('Text decoding options do not apply to Excel')
        rows, indices, sheet = xlsx_rows(path, options.get('sheet'))
    elif suffix in ('.csv', '.tsv', '.txt', '.dpt'):
        if 'sheet' in options:
            raise ValueError('sheet only applies to Excel')
        delimiter = options.get('delimiter', ',' if suffix == '.csv' else '\t' if suffix == '.tsv' else None)
        if delimiter is None or delimiter != 'whitespace' and (not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n'):
            raise ValueError('TXT requires an explicit delimiter or whitespace mode')
        encoding = options.get('encoding', 'utf-8-sig')
        if not isinstance(encoding,str) or not encoding.strip():
            raise ValueError('encoding must be a nonempty codec name')
        try:
            text = Path(path).read_text(encoding=encoding)
        except LookupError as exc:
            raise ValueError('Unknown text encoding: '+encoding) from exc
        try:
            rows = [line.split() for line in text.splitlines()] if delimiter == 'whitespace' else list(csv.reader(io.StringIO(text), delimiter=delimiter, strict=True))
        except csv.Error as exc:
            raise ValueError('Malformed delimited text: '+str(exc)) from exc
        indices = list(range(1, len(rows) + 1))
        sheet = None
    else:
        raise ValueError('Unsupported format; export a flat CSV/TSV/TXT/XLSX table first')
    if skip >= len(rows):
        raise ValueError('No table remains after declared skipped records')
    skipped = indices[:skip]
    rows, indices = rows[skip:], indices[skip:]
    if header:
        if 'names' in options:
            raise ValueError('names only applies to a headerless table')
        headers, rows, indices = rows[0], rows[1:], indices[1:]
    else:
        headers = options.get('names')
    if not isinstance(headers, list) or not headers or any(not isinstance(n, str) or not n.strip() for n in headers) or len(set(headers)) != len(headers):
        raise ValueError('Table headers must be explicit, nonempty and unique')
    if not rows:
        raise ValueError('Table contains no observations')
    for i, row in zip(indices, rows):
        if suffix == '.xlsx' and len(row) < len(headers):
            row.extend([''] * (len(headers) - len(row)))  # absence remains empty, never zero
        if len(row) != len(headers):
            raise ValueError('Table width mismatch at source record ' + str(i))
    return headers, rows, {'sheet': sheet, 'source_records': indices, 'declared_skipped_records': skipped,
                           'text_record_indices_are_csv_records_not_physical_lines': suffix != '.xlsx',
                           'options': options}


def finite(value):
    try:
        number = float(value)
        if number == 0 and Decimal(str(value)) != 0:
            return None  # Keep the lexeme in audit; never silently plot it as zero.
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError, InvalidOperation):
        return None


def profile(values, numeric=False, source_records=None):
    records = list(range(1, len(values) + 1)) if source_records is None else source_records
    if len(records) != len(values):
        raise ValueError('Profile records must match retained observations')
    missing = [records[i] for i, value in enumerate(values) if not value.strip()]
    result = {'observations': len(values), 'missing_count': len(missing), 'missing_record_indices': missing,
              'record_index_space': 'retained_observation_1_based' if source_records is None else 'source_records',
              'distinct_nonempty_lexemes': len({v for v in values if v.strip()})}
    if numeric:
        numbers = [finite(v) for v in values]
        bad = [records[i] for i, v in enumerate(numbers) if v is None and values[i].strip()]
        valid = [n for n in numbers if n is not None]
        result.update(nonfinite_or_nonnumeric_count=len(bad), invalid_record_indices=bad, finite_count=len(valid),
                      range=[min(valid), max(valid)] if valid else None,
                      mean_finite_only=mean(valid) if valid else None)
        deltas = [b - a for a, b in zip(numbers, numbers[1:]) if a is not None and b is not None]
        finite_deltas = [v for v in deltas if math.isfinite(v)]
        signs = [1 if v > 0 else -1 for v in finite_deltas if v != 0]
        result['sampling'] = {'adjacent_finite_pairs': len(deltas), 'zero_steps': deltas.count(0),
                              'step_range': [min(finite_deltas), max(finite_deltas)] if finite_deltas else None,
                              'overflow_steps': len(deltas) - len(finite_deltas),
                              'direction_changes': sum(a != b for a, b in zip(signs, signs[1:])),
                              'scope': 'stored order; pooled across rows, including group boundaries'}
    return result


def cv_summary(rows, columns, request):
    keys(request, ['kind', 'scan_rate_V_s', 'closure_tolerance_V', 'mass_g', 'area_cm2'], 'analysis')
    if request.get('kind') != 'cv_loop_capacitance':
        raise ValueError('Unsupported analysis; no automatic fitting or parameter extraction')
    rate, tolerance = request.get('scan_rate_V_s'), request.get('closure_tolerance_V', 1e-9)
    for name, value in [('scan_rate_V_s', rate), ('closure_tolerance_V', tolerance)]:
        if type(value) not in (int, float) or finite(value) is None or value <= 0:
            raise ValueError('Explicit positive ' + name + ' is required')
    rate, tolerance = finite(rate), finite(tolerance)
    factors = {'voltage': {'V': 1., 'mV': .001}, 'current': {'A': 1., 'mA': .001, 'uA': 1e-6, 'µA': 1e-6}}
    try:
        vx = factors['voltage'][columns['voltage']['unit']]
        iy = factors['current'][columns['current']['unit']]
        raw_potential = [finite(row['voltage']) for row in rows]
        raw_current = [finite(row['current']) for row in rows]
    except (KeyError, ValueError) as exc:
        raise ValueError('CV requires finite voltage/current and declared V/mV, A/mA/uA units') from exc
    if len(rows) < 3 or any(v is None for v in raw_potential + raw_current):
        raise ValueError('CV requires at least three finite source nodes')
    potential = [v * vx for v in raw_potential]
    current = [v * iy for v in raw_current]
    if any(raw != 0 and converted == 0 for raw, converted in zip(raw_potential + raw_current, potential + current)):
        raise ValueError('CV unit conversion underflow')
    differences = [b - a for a, b in zip(potential, potential[1:])]
    directions = [1 if d > 0 else -1 for d in differences if d != 0]
    if not directions or sum(a != b for a, b in zip(directions, directions[1:])) != 1 or abs(potential[-1] - potential[0]) > tolerance:
        raise ValueError('CV quotient requires one complete cycle with one reversal and potential closure')
    window = max(potential) - min(potential)
    denominator = 2 * rate * window
    if not math.isfinite(window) or not math.isfinite(denominator) or denominator <= 0:
        raise ValueError('CV analysis scale overflow/underflow')
    terms = []
    for a, b, dx in zip(current, current[1:], differences):
        # Form the mean in a normal exponent range; postpone rounding tiny
        # means until after multiplication by dV. Halving subnormals first
        # can lose part of a representable trapezoid even when it stays nonzero.
        exponent = max((math.frexp(v)[1] for v in (a, b) if v != 0), default=0)
        average = (math.ldexp(a, -exponent) + math.ldexp(b, -exponent)) / 2
        dx_mantissa, dx_exponent = math.frexp(dx)
        try:
            term = math.ldexp(average * dx_mantissa, exponent + dx_exponent)
        except OverflowError as exc:
            raise ValueError('CV analysis integral overflow') from exc
        if dx != 0 and ((average == 0 and a != -b) or (average != 0 and term == 0)):
            raise ValueError('CV analysis integral underflow')
        terms.append(term)
    if not all(math.isfinite(v) for v in terms):
        raise ValueError('CV analysis integral overflow')
    try:
        integral = math.fsum(terms)
    except OverflowError as exc:
        raise ValueError('CV analysis integral overflow') from exc
    capacitance = abs(integral) / denominator
    if integral != 0 and capacitance == 0:
        raise ValueError('CV analysis quotient underflow')
    if not math.isfinite(capacitance):
        raise ValueError('CV analysis overflow')
    result = {'method': 'stored-order trapezoidal closed-loop integral; no sorting, peak subtraction or interpolation',
              'signed_loop_integral_A_V': integral, 'absolute_loop_integral_A_V': abs(integral),
              'potential_window_V': window, 'scan_rate_V_s': rate, 'closure_tolerance_V': tolerance,
              'formula': 'C_apparent = abs(integral(I dV)) / (2 * scan_rate * potential_window)',
              'apparent_capacitance_F': capacitance, 'analysis_only_unit_factors': {'voltage': vx, 'current': iy},
              'claim': 'Loop quotient only; Faradaic/irreversible currents may contribute. Not proof of double-layer capacitance, ECSA or a fitted mechanism.'}
    for key, unit in [('mass_g', 'F_g'), ('area_cm2', 'F_cm2')]:
        if key in request:
            value = request[key]
            if type(value) not in (int, float) or finite(value) is None or value <= 0:
                raise ValueError('Explicit positive normalization basis required: ' + key)
            value = finite(value)
            quotient = capacitance / value
            if capacitance != 0 and quotient == 0:
                raise ValueError('CV normalization underflow')
            if not math.isfinite(quotient):
                raise ValueError('CV normalization overflow')
            result['apparent_capacitance_' + unit] = quotient
            result[key] = value
    return result


def convert(source, mapping_path, out):
    source, mapping_path, out = Path(source), Path(mapping_path), Path(out)
    if out.exists() or out.is_symlink():
        raise FileExistsError('Refusing to overwrite an intake generation')
    source_hash, mapping_hash = sha(source), sha(mapping_path)
    contract = load_json(mapping_path)
    keys(contract, ['schema_version', 'table', 'profile', 'columns', 'metadata', 'plot', 'analysis', 'synthetic'], 'mapping')
    if type(contract.get('schema_version')) is not int or contract['schema_version'] != 1:
        raise ValueError('Expected intake schema_version=1')
    if type(contract.get('synthetic', False)) is not bool:
        raise ValueError('synthetic must be boolean')
    columns = contract.get('columns')
    if not isinstance(columns, dict) or not columns:
        raise ValueError('Explicit column mapping is required')
    headers, raw, provenance = read_table(source, contract.get('table'))
    for role, spec in columns.items():
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,47}', role) or role == 'source_record':
            raise ValueError('Invalid mapped role')
        keys(spec, ['source', 'unit', 'type'], 'column')
        if spec.get('source') not in headers or spec.get('type') not in ('numeric', 'text'):
            raise ValueError('Missing source column or explicit column type: ' + role)
        if spec['type'] == 'numeric' and (not isinstance(spec.get('unit'), str) or not spec['unit'].strip()):
            raise ValueError('Numeric columns require a declared unit (1 for dimensionless): ' + role)
    metadata = contract.get('metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError('metadata must be an object')
    kind = contract.get('profile', 'generic')
    if kind not in ('generic', 'battery', 'xps', 'spectrum'):
        raise ValueError('Unknown intake profile')
    required = set()
    if kind == 'battery':
        if metadata.get('level') not in ('record', 'step', 'cycle') or not isinstance(metadata.get('current_sign_convention'),str) or not metadata['current_sign_convention'].strip():
            raise ValueError('Battery export requires record/step/cycle level and current sign convention')
        required = {'sample', 'channel', 'cycle'}
        if metadata['level'] == 'record':
            required |= {'step', 'branch', 'time', 'voltage', 'current'}
        if metadata['level'] == 'step':
            required |= {'step', 'branch'}
    if kind == 'xps':
        required = {'sample', 'region', 'energy', 'intensity'}
        if metadata.get('energy_type') not in ('binding', 'kinetic') or metadata.get('scan_type') not in ('survey', 'high_resolution', 'mixed') or not isinstance(metadata.get('processing'),str) or not metadata['processing'].strip():
            raise ValueError('XPS requires explicit energy type, scan type and previous processing')
        if columns.get('energy', {}).get('unit') != 'eV' or columns.get('intensity', {}).get('unit') not in ('counts', 'CPS'):
            raise ValueError('XPS energy eV and intensity counts/CPS must be explicit')
    if not required <= set(columns):
        raise ValueError('Missing required mapped identities/observables: ' + ', '.join(sorted(required - set(columns))))
    for role in required & {'time', 'voltage', 'current', 'energy', 'intensity'}:
        if columns[role]['type'] != 'numeric':
            raise ValueError('Observable columns must be numeric: ' + role)
    for role in required & {'sample', 'channel', 'cycle', 'step', 'branch', 'region'}:
        if columns[role]['type'] != 'text':
            raise ValueError('Identity columns must remain text: ' + role)
    mapped = [{role: row[headers.index(spec['source'])] for role, spec in columns.items()} for row in raw]
    profiles = {role: profile([row[role] for row in mapped], spec['type'] == 'numeric', provenance['source_records'])
                for role, spec in columns.items()}
    identity_roles = required & {'sample', 'channel', 'cycle', 'step', 'branch', 'region'}
    if any(profiles[role]['missing_count'] for role in identity_roles):
        raise ValueError('Missing sample/channel/cycle/step/branch/region identity')
    plotting = contract.get('plot')
    grouping = []
    if plotting is not None:
        keys(plotting, ['x', 'y', 'group_by', 'x_label', 'y_label', 'kind', 'marker_size_pt'], 'plot')
        grouping = plotting.get('group_by', [])
        if not isinstance(grouping, list) or any(not isinstance(v, str) for v in grouping) or len(grouping) != len(set(grouping)) or not set(grouping) <= set(columns):
            raise ValueError('Invalid explicit plot grouping')
        minimal = {'sample', 'channel'} if kind == 'battery' else {'sample', 'region'} if kind == 'xps' else set()
        if not minimal <= set(grouping):
            raise ValueError('Plot grouping must keep sample/channel or sample/region separate')
        if not isinstance(plotting.get('y'), list) or not plotting['y'] or any(not isinstance(v, str) for v in plotting['y']) or len(set(plotting['y'])) != len(plotting['y']):
            raise ValueError('Plot y must be a nonempty unique role list')
        selected = [plotting.get('x')] + plotting['y']
        for role in selected:
            if not isinstance(role, str) or role not in columns or columns[role]['type'] != 'numeric' or profiles[role]['missing_count'] or profiles[role]['nonfinite_or_nonnumeric_count']:
                raise ValueError('Plot requires complete finite numeric roles; audit-only intake preserves missing/invalid data')
    grouped = {}
    for row, index in zip(mapped, provenance['source_records']):
        key = tuple(row[role] for role in grouping)
        grouped.setdefault(key, []).append((row, index))
    if len(grouped) > 128:
        raise ValueError('More than 128 groups; select a bounded task explicitly')
    analysis = None
    if 'analysis' in contract:
        if len(grouped) != 1:
            raise ValueError('CV analysis requires one explicitly selected sample/cycle; no pooled quotient')
        # Even audit-only analyses must not mix specimen/channel/cycle identities.
        for role in ('sample', 'channel', 'cycle'):
            if role in columns and len({row[role] for row in mapped}) > 1:
                raise ValueError('CV analysis cannot pool multiple sample/channel/cycle identities')
        analysis = cv_summary(mapped, columns, contract['analysis'])
    report = {'schema_version': 1, 'source_rows': len(raw), 'source_columns': headers, 'mapping': contract,
              'source_provenance': provenance, 'columns': profiles,
              'exact_duplicate_rows': len(raw) - len({tuple(row) for row in raw}),
              'summary_scope': 'Finite observations only for numeric summaries; no filtering of exported rows; counts are observations, not independent replicates',
              'processing': 'No sorting, filtering, filling, smoothing, normalization, calibration, background subtraction or fitting',
              'analysis': analysis, 'grouping': grouping,
              'groups': [{'identity': dict(zip(grouping, key)), 'rows': len(rows)} for key, rows in grouped.items()]}
    config = {'schema_version': 1, 'plots': []}
    if plotting is not None:
        module = importlib.util.spec_from_file_location('intake_plotter', Path(__file__).with_name('ai2origin.py'))
        draw = importlib.util.module_from_spec(module)
        module.loader.exec_module(draw)
        style, _ = draw.STYLE.resolve(draw.load_json)
        for index, (identity, rows) in enumerate(grouped.items(), 1):
            spec = {'id': 'input' + str(index), 'csv': 'input' + str(index) + '.csv', 'kind': plotting.get('kind', 'line_symbol'),
                    'x': plotting['x'], 'connect_order': 'acquisition', 'synthetic': contract.get('synthetic', False),
                    'labels': {'x': plotting.get('x_label', plotting['x'] + ' (' + columns[plotting['x']]['unit'] + ')'),
                               'y': plotting.get('y_label', ' / '.join(role + ' (' + columns[role]['unit'] + ')' for role in plotting['y']))},
                    'series': [{'column': role, 'label': role} for role in plotting['y']],
                    'caption': 'Explicit flat-table mapping; stored order and values retained. Prior processing: ' + str(metadata.get('processing', 'as supplied'))}
            if len({columns[role]['unit'] for role in plotting['y']}) != 1:
                raise ValueError('Different y units require separate plots, not silent normalization')
            if spec['kind'] not in ('line', 'line_symbol', 'scatter'):
                raise ValueError('Intake implements XY plots only; choose another adapter explicitly')
            if 'marker_size_pt' in plotting:
                config['style'] = {'marker': {'size_pt': plotting['marker_size_pt']}}
                style, _ = draw.STYLE.resolve(draw.load_json, project=config['style'])
            draw.prepare_plot(spec, [row for row, _ in rows], index, style)
            config['plots'].append(spec)
    if sha(source) != source_hash or sha(mapping_path) != mapping_hash:
        raise ValueError('Source/mapping changed during intake; no output accepted')
    out.mkdir(parents=True)
    try:
        def write_csv(name, names, values):
            with (out / name).open('w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, lineterminator='\n'); writer.writerow(names); writer.writerows(values)
        write_csv('source-table.csv', headers, raw)
        write_csv('mapped.csv', ['source_record'] + list(columns), [[index] + list(row.values()) for row, index in zip(mapped, provenance['source_records'])])
        if plotting is not None:
            for index, rows in enumerate(grouped.values(), 1):
                write_csv('input' + str(index) + '.csv', list(columns), [list(row.values()) for row, _ in rows])
            (out / 'plot.json').write_text(json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        (out / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        receipt = {'schema_version': 1, 'status': 'INTAKE_COMPLETE', 'generator': 'Ai2origin ' + VERSION,
                   'processor_sha256': sha(__file__), 'source': {'name': source.name, 'sha256': source_hash},
                   'mapping_sha256': mapping_hash, 'rows': len(raw),
                   'outputs': [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(out.iterdir())]}
        (out / 'intake-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    except Exception:
        (out / 'FAILED.json').write_text('{"status":"FAILED_INTAKE"}\n', encoding='utf-8')
        raise
    return {'status': 'INTAKE_COMPLETE', 'rows': len(raw), 'plots': len(config['plots']), 'scientific_validation': 'NOT_CLAIMED'}


def verify(folder, repeat=None):
    folder = Path(folder)
    receipt = load_json(folder / 'intake-receipt.json')
    if receipt.get('status') != 'INTAKE_COMPLETE':
        raise ValueError('Incomplete intake generation')
    outputs = receipt.get('outputs', [])
    names = [v['name'] for v in outputs]
    if not names or len(names) != len(set(names)) or not {'source-table.csv', 'mapped.csv', 'summary.json'} <= set(names):
        raise ValueError('Incomplete intake inventory')
    for entry in outputs:
        name = entry['name']; p = folder / name
        if Path(name).name != name or not p.is_file() or p.is_symlink() or p.stat().st_size != entry['bytes'] or sha(p) != entry['sha256']:
            raise ValueError('Intake output hash/size/path mismatch')
    report = load_json(folder / 'summary.json')
    expected = {'source-table.csv', 'mapped.csv', 'summary.json'}
    if report['mapping'].get('plot') is not None:
        expected |= {'plot.json'} | {'input' + str(i) + '.csv' for i in range(1, len(report['groups']) + 1)}
    if set(names) != expected:
        raise ValueError('Intake inventory differs from requested plot generation')
    for p in folder.iterdir():
        if not p.is_file() or p.is_symlink() or p.name not in set(names) | {'intake-receipt.json'}:
            raise ValueError('Unexpected intake output entry')
    result = {'status': 'PASS', 'files_verified': len(names), 'scientific_validation': 'NOT_CLAIMED'}
    if repeat is not None:
        verify(repeat)
        if receipt != load_json(Path(repeat) / 'intake-receipt.json'):
            raise ValueError('Intake repeat receipt/output identity differs')
        result['repeat'] = 'BYTE_IDENTICAL'
    return result


def inspect_sources(paths, options=None):
    """Bounded, read-only routing before the author/agent defines semantics."""
    if not 1 <= len(paths) <= 32:
        raise ValueError('Inspect 1..32 explicitly selected files at a time')
    results = []
    for path in map(Path, paths):
        if not path.is_file(): raise ValueError('Inspect requires files, not directory traversal: ' + path.name)
        item = {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path),
                'scientific_validation': 'NOT_CLAIMED', 'status': 'HOLD_ADAPTER'}
        suffix = path.suffix.lower()
        if suffix in ('.csv', '.tsv', '.txt', '.dpt', '.xlsx'):
            try:
                if path.stat().st_size > 64*1024*1024:
                    raise ValueError('Quick inspection is limited to 64 MiB per table; use a bounded format-specific parser')
                headers, rows, info = read_table(path, options)
                item.update(status='TABLE_INSPECTED', route='explicit column/unit mapping with intake.py',
                            headers=headers, rows=len(rows), preview=rows[:3], provenance=info,
                            columns={h: profile([r[i] for r in rows], numeric=True)
                                     for i,h in enumerate(headers)},
                            reminder='Numeric candidates are not confirmed physical quantities or units; no mapping or transformation applied.')
                # Avoid repeating one row index per observation in a quick inventory.
                item['provenance'] = {k:v for k,v in info.items() if k != 'source_records'}
                item['provenance']['record_count'] = len(info['source_records'])
                for summary in item['columns'].values():
                    for key in ('missing_record_indices', 'invalid_record_indices'):
                        summary[key] = summary[key][:16]
                    summary['index_preview_limit'] = 16
            except (ValueError, KeyError, OSError, ET.ParseError, zipfile.BadZipFile) as exc:
                item.update(status='HOLD_TABLE_OPTIONS_OR_ADAPTER', reason=str(exc))
        elif suffix in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'):
            from PIL import Image
            try:
                with Image.open(path) as image:
                    item.update(dimensions=list(image.size), image_format=image.format)
                    image.verify()
                item.update(status='IMAGE_REFERENCE_ONLY', route='inspect image; numeric digitization requires calibration and disclosure')
            except (OSError, ValueError) as exc:
                item.update(status='HOLD_INVALID_IMAGE', reason=str(exc))
        elif suffix in ('.opj', '.opju'):
            item['route'] = 'native project adapter on a protected copy; inspect actual worksheet/graph bindings'
        else:
            item['route'] = 'identify format and use a validated owner parser; never rename to CSV'
        if sha(path) != item['sha256']: raise ValueError('Input changed during inspection: ' + path.name)
        results.append(item)
    return {'status':'INSPECTED_NO_OUTPUT_FILES', 'files':results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, nargs='?')
    parser.add_argument('--map', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--check', type=Path)
    parser.add_argument('--repeat', type=Path)
    parser.add_argument('--inspect', type=Path, nargs='+', help='Read-only inventory of up to 32 supplied files; no automatic scientific mapping')
    parser.add_argument('--table', type=Path, help='Explicit table-options JSON for --inspect (delimiter, encoding, header, sheet)')
    args = parser.parse_args(argv)
    try:
        if args.inspect:
            if args.source or args.map or args.out or args.check or args.repeat:
                parser.error('--inspect accepts only --table')
            result = inspect_sources(args.inspect, load_json(args.table) if args.table else None)
        elif args.table:
            parser.error('--table requires --inspect')
        elif args.check:
            if args.source or args.map or args.out:
                parser.error('--check only accepts --repeat')
            result = verify(args.check, args.repeat)
        else:
            if not args.source or not args.map or not args.out or args.repeat:
                parser.error('Conversion requires source, --map and --out')
            result = convert(args.source, args.map, args.out)
        print(json.dumps(result))
    except (ValueError, KeyError, OSError, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(1, 'FAIL: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
