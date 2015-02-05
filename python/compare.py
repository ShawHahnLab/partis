#!/usr/bin/env python

import argparse
import json
import csv
import sys
sys.path.append('python')

import plotting
import utils
from opener import opener

parser = argparse.ArgumentParser()
parser.add_argument('-b', action='store_true')  # passed on to ROOT when plotting
parser.add_argument('--outdir', required=True)
parser.add_argument('--plotdirs', required=True)
parser.add_argument('--names', required=True)
parser.add_argument('--stats', default='')
parser.add_argument('--no-errors', action='store_true')
parser.add_argument('--plot-performance', action='store_true')
parser.add_argument('--scale-errors', type=float)
parser.add_argument('--rebin', type=int)
parser.add_argument('--colors')
parser.add_argument('--linestyles')
parser.add_argument('--datadir', default='data/imgt')
parser.add_argument('--leaves-per-tree')
parser.add_argument('--linewidth')
parser.add_argument('--markersize')
parser.add_argument('--dont-calculate-mean-info', action='store_true')
parser.add_argument('--normalize', action='store_true')

args = parser.parse_args()
args.plotdirs = utils.get_arg_list(args.plotdirs)
args.colors = utils.get_arg_list(args.colors, intify=True)
args.linestyles = utils.get_arg_list(args.linestyles, intify=True)
args.names = utils.get_arg_list(args.names)
args.leaves_per_tree = utils.get_arg_list(args.leaves_per_tree, intify=True)
for iname in range(len(args.names)):
    args.names[iname] = args.names[iname].replace('@', ' ')

assert len(args.plotdirs) == len(args.names)

with opener('r')(args.datadir + '/v-meta.json') as json_file:  # get location of <begin> cysteine in each v region
    args.cyst_positions = json.load(json_file)
with opener('r')(args.datadir + '/j_tryp.csv') as csv_file:  # get location of <end> tryptophan in each j region (TGG)
    tryp_reader = csv.reader(csv_file)
    args.tryp_positions = {row[0]:row[1] for row in tryp_reader}  # WARNING: this doesn't filter out the header line

plotting.compare_directories(args)
