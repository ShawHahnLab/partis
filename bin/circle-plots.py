#!/usr/bin/env python3
from __future__ import absolute_import, division
import sys
import colored_traceback.always
import os
import circlify
import json
import argparse
from backports import csv
from io import open

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('infname')
parser.add_argument('outfname')
args = parser.parse_args()

radii = []
with open(args.infname) as ifile:
    reader = csv.DictReader(ifile)
    for line in reader:
        radii.append({'id' : line['id'], 'radius' : float(line['radius'])})

circlefos = circlify.circlify(radii, datum_field='radius', id_field='id')  # NOTE this doesn't return them in the same order
with open(args.outfname, 'w') as ofile:
    def gfn(k, c): return getattr(c, k) if hasattr(c, k) else getattr(c, 'ex')[k]
    headers = ('id', 'x', 'y', 'r')
    writer = csv.DictWriter(ofile, headers)
    writer.writeheader()
    for cfo in circlefos:
        writer.writerow({k : gfn(k, cfo) for k in headers})
