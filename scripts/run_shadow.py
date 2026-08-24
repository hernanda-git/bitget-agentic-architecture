"""Shadow runner entrypoint. Default is fixture mode and places zero orders."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ledger.sqlite import EventLedger

def run_shadow(output: Path) -> dict:
    ledger=EventLedger(output)
    ledger.append('SHADOW_STARTED', {'mode':'shadow','orders_placed':0,'signed_calls':0})
    report={'mode':'shadow','orders_placed':0,'signed_calls':0,'status':'SHADOW_ONLY'}
    ledger.append('SHADOW_FINISHED', report)
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', default='data/shadow.sqlite3')
    args=parser.parse_args()
    print(json.dumps(run_shadow(Path(args.output)), sort_keys=True))

if __name__=='__main__': main()
