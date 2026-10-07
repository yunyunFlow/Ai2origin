#!/usr/bin/env python3
"""Read-only receipt/hash, source, SVG-text and repeat-output verification."""
import argparse
import base64
import csv
import hashlib
import json
import struct
from pathlib import Path
from xml.etree import ElementTree as ET


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate receipt/plan key: ' + key)
            result[key] = value
        return result
    def bad(value): raise ValueError('Non-finite JSON constant: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique, parse_constant=bad)


def inspect(folder,config=None):
    folder=Path(folder)
    if any((folder/name).exists() for name in ('FAILED.txt','FAILED.json')):
        raise ValueError('Generation has a failure marker: '+str(folder))
    native=(folder/'native-receipt.json').is_file()
    receipt_path=folder/('native-receipt.json' if native else 'receipt.json')
    receipt=load_json(receipt_path)
    if receipt['status'] not in ('NATIVE_EXPORTED','PREPARED','PYTHON_RENDERED'):
        raise ValueError('Unaccepted generation status')
    if native!=(receipt['status']=='NATIVE_EXPORTED'):
        raise ValueError('Receipt filename/backend status mismatch')
    if native and config is not None:
        raise ValueError('--config requires a prepared/Python generation; native provenance binds the prepared plan hash')
    files={}
    if not receipt['outputs']:raise ValueError('Empty output receipt')
    for entry in receipt['outputs']:
        name=entry['name']
        if not isinstance(name,str) or not name or '/' in name or '\\' in name or ':' in name or Path(name).name!=name or name.casefold() in {n.casefold() for n in files}:raise ValueError('Unsafe or duplicate receipt output')
        path=folder/name
        if not path.is_file() or path.is_symlink() or sha(path)!=entry['sha256'] or path.stat().st_size!=entry['bytes']:
            raise ValueError('Output hash/size mismatch: '+name)
        files[name]=entry['sha256']
        if path.suffix=='.svg':
            tree=ET.parse(path)
            if not any(node.tag.rsplit('}',1)[-1]=='text' for node in tree.iter()):
                raise ValueError('SVG contains no editable text: '+name)
    metadata = {'_session.json', '_assets.json'} if native else set()
    if native:
        metadata.update(name[:-4] + '-layout.json' for name in files
                        if name.endswith('.png') and not name.endswith('-reopened.png')
                        and not name.startswith('_layout-'))
    allowed = set(files) | metadata | {receipt_path.name}
    for path in folder.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError('Unexpected output entry: ' + path.name)
        if path.name not in allowed:
            raise ValueError('Unlisted output file: ' + path.name)
    if native:
        from PIL import Image,ImageChops
        names=[n for n in files if n.endswith('-reopened.png')]
        if not names or len(names)!=receipt['reopened_graph_count'] or receipt['project_reopen']!='PASS':
            raise ValueError('Saved-project graph count/status mismatch')
        if receipt['numeric_readback']!='PASS' or receipt['style_readback']!='PASS_BEFORE_AND_AFTER_REOPEN':
            raise ValueError('Native read-back acceptance missing')
        if 'figures.opju' not in files:raise ValueError('Saved native project missing')
        for name in names:
            original=name.replace('-reopened.png','.png')
            if original not in files:raise ValueError('Original native export missing')
            with Image.open(folder/original) as a,Image.open(folder/name) as b:
                if a.size!=b.size or ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox() is not None:
                    raise ValueError('Reopened RGB pixels changed: '+original)
        if receipt['numeric_readback_cells']!=receipt['reopened_readback_cells']:
            raise ValueError('Saved worksheet cell counts differ')
    else:
        if 'origin-plan.json' not in files:raise ValueError('Prepared plan is not hash-bound')
        plan=load_json(folder/'origin-plan.json')
        ids=[plot['id'] for plot in plan['plots']]
        if not ids or len(set(ids))!=len(ids):raise ValueError('Empty or duplicate prepared plot inventory')
        selected=plan.get('selected_plot_ids')
        if selected is not None and (not isinstance(selected,list) or selected!=ids):
            raise ValueError('Declared recipe selection differs from prepared inventory')
        for plot in plan['plots']:
            if not plot.get('books'):raise ValueError('Prepared plot has no worksheets')
            for book in plot['books']:
                if plot['id']+'-'+book['name']+'.csv' not in files:
                    raise ValueError('Prepared worksheet CSV missing: '+book['name'])
                if 'data_f64le' in book:
                    raw = base64.b64decode(book['data_f64le'], validate=True)
                    values = [0.0 if v is None else float(v) for row in book['rows'] for v in row]
                    if raw != struct.pack('<' + 'd'*len(values), *values):
                        raise ValueError('Exact worksheet payload differs from JSON geometry')
                    with (folder/(plot['id']+'-'+book['name']+'.csv')).open(encoding='utf-8',newline='') as handle:
                        table = list(csv.reader(handle, strict=True))
                    expected = [[ '' if v is None else format(float(v),'.17g') for v in row] for row in book['rows']]
                    if table != [book['headers']] + expected:
                        raise ValueError('Prepared worksheet CSV differs from bound geometry')
            asset=plot.get('metadata',{}).get('colorbar_asset')
            if asset is not None and files.get(asset['name'])!=asset['sha256']:
                raise ValueError('Prepared colorbar asset missing or changed')
        if config is not None:
            config=Path(config).resolve();source=load_json(config)
            if sha(config)!=plan['config_sha256']:raise ValueError('Config hash mismatch')
            project_style=[v for v in plan.get('style_inputs',[]) if v['layer']=='project-file']
            if source.get('style_file'):
                path=config.parent/source['style_file']
                if len(project_style)!=1 or path.name!=project_style[0]['file_name'] or sha(path)!=project_style[0]['sha256']:
                    raise ValueError('Project style-file hash mismatch')
            mapped={q['id']:q for q in source['plots']}
            if len(mapped)!=len(source['plots']):raise ValueError('Duplicate source recipe IDs')
            if selected is not None:
                if not set(selected).issubset(mapped) or selected != [p['id'] for p in source['plots'] if p['id'] in selected]:
                    raise ValueError('Selected recipes differ from catalog order/inventory')
                mapped={key:mapped[key] for key in selected}
            if set(mapped)!=set(ids):
                raise ValueError('Config/plan plot inventory mismatch')
            for plot in plan['plots']:
                path=config.parent/mapped[plot['id']]['csv']
                if sha(path)!=plot['metadata']['source_sha256']:raise ValueError('Source CSV hash mismatch: '+path.name)
        if receipt['status']=='PYTHON_RENDERED':
            if 'python_layout_checks' in receipt:
                checks=receipt['python_layout_checks']
                if not isinstance(checks,dict) or set(checks)!=set(ids):
                    raise ValueError('Python layout report inventory differs')
                for identity in ids:
                    name=identity+'-layout.json'
                    if name not in files:raise ValueError('Python layout report missing: '+name)
                    layout=load_json(folder/name)
                    status='NEEDS_REVIEW' if (layout['legend_collisions'] or layout['text_outside_canvas']
                                             or layout.get('geometry_unchecked')) else 'NO_GEOMETRIC_ISSUES_DETECTED'
                    if (layout.get('backend')!='PYTHON' or layout.get('plot_id')!=identity
                            or layout.get('visual_review')!='REQUIRED'
                            or layout.get('status')!=status or checks[identity]!=status):
                        raise ValueError('Python layout report status differs')
            # Old receipts explicitly predate the PNG-only default and required both.
            formats=receipt.get('python_export_formats',['png','svg'])
            if formats not in (['png'],['png','svg']):
                raise ValueError('Invalid declared Python export formats')
            for plot in plan['plots']:
                for suffix in formats:
                    if plot['id']+'.'+suffix not in files:
                        raise ValueError('Rendered plot outputs missing: '+plot['id']+'.'+suffix)
                if formats==['png'] and plot['id']+'.svg' in files:
                    raise ValueError('SVG output was not declared')
    return receipt,files


def check(first,second=None,config=None):
    if (Path(first)/'analysis-receipt.json').is_file():
        import importlib.util
        source=Path(__file__).with_name('analyze.py')
        spec=importlib.util.spec_from_file_location('ai2origin_analysis_check',source)
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
        return value.verify(first,second,config)
    receipt,files=inspect(first,config)
    result={'status':'PASS','files_verified':len(files),'backend':receipt['status'],
            'visual_review':'REQUIRED','scientific_validation':'NOT_CLAIMED'}
    if second is not None:
        other,comparison=inspect(second,config)
        if receipt['status']!=other['status']:raise ValueError('Cannot compare different backends/statuses')
        if receipt['status']=='NATIVE_EXPORTED':
            from PIL import Image,ImageChops
            # OPJU can contain session/time metadata. Compare its provenance
            # and all visible exports, without requiring project byte identity.
            for key in ('plan_sha256','runner_sha256','origin_version','numeric_readback_cells'):
                if receipt[key]!=other[key]:raise ValueError('Native provenance differs: '+key)
            if set(files)!=set(comparison):raise ValueError('Native repeat output inventory differs')
            for name in files:
                if name.endswith('.png') and not name.startswith('_layout-'):
                    with Image.open(Path(first)/name) as a,Image.open(Path(second)/name) as b:
                        if a.size!=b.size or ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox():
                            raise ValueError('Native repeat RGB pixels changed: '+name)
            result['repeat']='NATIVE_RGB_IDENTICAL'
        else:
            if files!=comparison:raise ValueError('Repeat output hashes differ')
            if receipt!=other:raise ValueError('Repeat receipts/environment differ')
            result['repeat']='BYTE_IDENTICAL'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first',type=Path);parser.add_argument('second',type=Path,nargs='?')
    parser.add_argument('--config',type=Path,help='Optional original source/config identity check')
    args=parser.parse_args()
    try:print(json.dumps(check(args.first,args.second,args.config)))
    except (ValueError,KeyError,OSError,ET.ParseError) as exc:parser.exit(1,'FAIL: '+str(exc)+'\n')


if __name__=='__main__':main()
