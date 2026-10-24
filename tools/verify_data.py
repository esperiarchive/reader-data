"""Verify a standalone reader-data checkout using only Python's standard library."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import argparse


def safe_path(root, name):
    if not isinstance(name,str) or '\\' in name or ':' in name or PurePosixPath(name).is_absolute() or any(part in {'','.','..'} for part in name.split('/')):
        raise ValueError('Unsafe manifest path: '+str(name))
    return root/name


def verify(root,workers=8):
    root=Path(root).resolve();release=json.loads((root/'release.json').read_bytes())
    expected={}
    for shard in release['file_manifests']:
        data=safe_path(root,shard['path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=shard['sha256']:raise ValueError('Manifest hash mismatch: '+shard['path'])
        files=json.loads(data)['files']
        if len(files)!=shard['files'] or expected.keys() & files.keys():raise ValueError('Duplicate/miscounted manifest entries')
        expected.update(files)
    actual=set()
    for folder,dirs,names in os.walk(root/'data'):
        for name in [*dirs,*names]:
            path=Path(folder)/name
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Linked data entry')
        actual.update((Path(folder)/name).relative_to(root/'data').as_posix() for name in names)
    if actual!=set(expected):raise ValueError(f'Data inventory differs: {len(actual-set(expected))} extra, {len(set(expected)-actual)} missing')
    if len(actual)!=len({name.casefold() for name in actual}):raise ValueError('Case collision')
    if len(actual)!=release['files']:raise ValueError('Release file count mismatch')
    def check(item):
        name,entry=item
        data=safe_path(root/'data',name).read_bytes()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Data hash mismatch: '+name)
        return len(data)
    total=0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for number,size in enumerate(pool.map(check,sorted(expected.items())),1):
            total+=size
            if number%25000==0:print(f'Verified JSON {number}/{len(expected)}',flush=True)
    if total!=release['bytes']:raise ValueError('Release byte count mismatch')
    if not safe_path(root,release['entrypoint']).is_file():raise ValueError('Missing entrypoint')
    return {'valid':True,'files':len(actual),'bytes':total,'manifest_shards':len(release['file_manifests']),
            'media_commit':release['media_commit'],'missing_files':0,'extra_files':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=verify(args.root);text=json.dumps(result,indent=2)+'\n'
    if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(text,encoding='utf-8')
    print(text)
