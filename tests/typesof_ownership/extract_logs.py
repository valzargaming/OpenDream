"""Strict bounded extraction of archived original logs. Never classifies native acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile
from archive_logs import NAMES, MAX_BYTES

def require(condition,message):
    if not condition:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def pairs(rows):
    result={}
    for key,value in rows:
        require(key not in result,'duplicate receipt key')
        result[key]=value
    return result
def extract(archive,receipt,destination):
    require(not archive.is_symlink() and archive.is_file() and 0<archive.stat().st_size<=4*MAX_BYTES+65536,'archive size/type')
    require(not receipt.is_symlink() and receipt.is_file() and 0<receipt.stat().st_size<=65536,'receipt size/type')
    record=json.loads(receipt.read_bytes(),object_pairs_hook=pairs)
    require(set(record)=={'schema','files','archive_sha256','scope'} and record['schema']==1,'receipt schema')
    require(record['scope']=='byte retention only; test acceptance remains strict TRX and original-log replay','receipt scope')
    require(tuple(record['files'])==NAMES,'receipt exact members/order')
    require(sha(archive.read_bytes())==record['archive_sha256'],'archive checksum')
    require(not destination.exists() and not destination.is_symlink(),'fresh extraction destination required')
    originals={}
    with zipfile.ZipFile(archive) as bundle:
        infos=bundle.infolist()
        require(tuple(i.filename for i in infos)==NAMES,'exact ZIP members/order; no traversal/duplicates/extras')
        for info in infos:
            file_type=stat.S_IFMT(info.external_attr>>16)
            require(file_type in (0,stat.S_IFREG) and not info.is_dir() and not info.flag_bits&1,'regular unencrypted ZIP member')
            require(info.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),'ZIP compression')
            row=record['files'][info.filename]
            require(set(row)=={'bytes','sha256'} and type(row['bytes']) is int and 0<row['bytes']<=MAX_BYTES,'member receipt')
            require(info.file_size==row['bytes'] and 0<=info.compress_size<=4*MAX_BYTES,'member bound')
            with bundle.open(info) as stream:raw=stream.read(MAX_BYTES+1)
            require(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'original log byte parity')
            originals[info.filename]=raw
    destination.mkdir(parents=True,exist_ok=False)
    for name,raw in originals.items():
        with (destination/name).open('xb') as stream:stream.write(raw)
    return record

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(extract(args.archive,args.receipt,args.destination)))
