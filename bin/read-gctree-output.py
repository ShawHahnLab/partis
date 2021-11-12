#!/usr/bin/env python
import glob
import sys
import csv
csv.field_size_limit(sys.maxsize)  # make sure we can write very large csv fields
import os
import copy
import argparse
import colored_traceback.always
import json

# if you move this script, you'll need to change this method of getting the imports
partis_dir = os.path.dirname(os.path.realpath(__file__)).replace('/bin', '')
sys.path.insert(1, partis_dir + '/python')

import utils
import paircluster
import glutils
from clusterpath import ClusterPath

helpstr = """
Run partis selection metrics on gctree output dir (gctree docs: https://github.com/matsengrp/gctree/).
Plots are written to <--outdir>/selection-metrics/plots.
Log files are written to <--outdir>; get-selection-metrics.log has most of the interesting information (view with less -RS).
Example usage:
  ./bin/read-gctree-output.py --seqfname <fasta-input-file> --gctreedir <gctree-output-dir> --outdir <dir-for-partis-output>
"""
class MultiplyInheritedFormatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass
formatter_class = MultiplyInheritedFormatter
parser = argparse.ArgumentParser(formatter_class=MultiplyInheritedFormatter, description=helpstr)
parser.add_argument('--actions', default='cache-parameters:annotate:get-selection-metrics')
# TODO handle single chain without setting --seqfname
parser.add_argument('--seqfname', required=True, help='fasta file with all input sequences (if --paired-loci is set, this should include, separately, all heavy and all light sequences, where the two sequences in a pair have identical uids [at least up to the first \'_\']). If single chain, this can just be the fasta corresponding to')
parser.add_argument('--gctreedir', required=True, help='gctree output dir (to get --tree-basename and abundances.csv')
parser.add_argument('--outdir', required=True, help='directory to which to write partis output files')
parser.add_argument('--input-partition-fname', help='partis style yaml file with a partition grouping seqs into clonal families; if set, input data is assumed to contain many families (if not set, we assume it\'s only one fmaily).')
parser.add_argument('--paired-loci', action='store_true', help='run on paired heavy/light data')
parser.add_argument('--locus', default='igh', choices=utils.loci)
parser.add_argument('--kdfname', help='csv file with kd values (and, optionally, multiplicities), with header names as specified in subsequent args.')
parser.add_argument('--name-column', default='name', help='column name in --kdfname from which to take sequence name')
parser.add_argument('--kd-columns', default='kd', help='colon-separated list of column name[s] in --kdfname from which to take kd values. If more than one, the values are added.')
parser.add_argument('--multiplicity-column', help='If set, column name in --kdfname from which to take multiplicity value. If not set, abundances are read from --gctreedir and converted to multiplicities.')
parser.add_argument('--dont-invert-kd', action='store_true', help='by default we invert (take 1/kd) to convert to \'affinity\' (after adding multiple kd columns, if specified), or at least something monotonically increasing with affinity. This skips that step, e.g. if you\'re passing in affinity.')
parser.add_argument('--species', default='mouse', choices=('human', 'macaque', 'mouse'))
parser.add_argument('--tree-basename', default='gctree.out.inference.1.nk', help='basename of tree file to take from --gctreedir')  # .1 is the most likely one (all trees are also in the pickle file as ete trees: gctree.out.inference.parsimony_forest.p
parser.add_argument('--abundance-basename', default='abundances.csv', help='basename of tree file to take from --gctreedir. Not used if multiplicities are read from kdfname')  # .1 is the most likely one (all trees are also in the pickle file as ete trees: gctree.out.inference.parsimony_forest.p
parser.add_argument('--dry', action='store_true')
args = parser.parse_args()
args.actions = utils.get_arg_list(args.actions)
args.kd_columns = utils.get_arg_list(args.kd_columns)
if not args.paired_loci:
    raise Exception('needs testing')

# ----------------------------------------------------------------------------------------
def metafname():
    return '%s/gctree-meta.yaml' % args.outdir

# ----------------------------------------------------------------------------------------
def run_cmd(action):
    locstr = '--paired-loci' if args.paired_loci else '--locus %s'%args.locus
    cmd = './bin/partis %s %s --species %s --guess-pairing-info --input-metafnames %s' % (action, locstr, args.species, metafname())
    if action in ['cache-parameters', 'annotate']:
        cmd += ' --infname %s' % args.seqfname
        if args.paired_loci:
            cmd += ' --paired-outdir %s' % args.outdir
        else:
            cmd += ' --parameter-dir %s/parameters' % args.outdir
    if action == 'annotate':
        if args.input_partition_fname is None:  # one gc at a time
            cmd += ' --all-seqs-simultaneous'
        else:  # many gcs together
            cmd += ' --input-partition-fname %s' % args.input_partition_fname
    if action in ['annotate', 'get-selection-metrics'] and '--paired-outdir' not in cmd:
        cmd += ' --%s %s%s' % ('paired-outdir' if args.paired_loci else 'outfname', args.outdir, '' if args.paired_loci else '/partition.yaml')
    if action == 'get-selection-metrics':
        cmd += ' --treefname %s/%s --plotdir %s --selection-metrics-to-calculate cons-dist-aa:lbi:aa-lbi:lbr:aa-lbr' % (args.gctreedir, args.tree_basename, 'paired-outdir' if args.paired_loci else '%s/selection-metrics/plots'%args.outdir)
        cmd += ' --queries-to-include-fname %s' % args.seqfname #  NOTE gets replaced in bin/partis  #paired-outdir' # % paircluster.paired_fn(args.outdir, 'igh')) #args.seqfname #
        cmd += ' --choose-all-abs --chosen-ab-fname %s/chosen-abs.csv --debug 1' % args.outdir
    utils.simplerun(cmd, logfname='%s/%s.log'%(args.outdir, action), dryrun=args.dry)

# ----------------------------------------------------------------------------------------
utils.mkdir(args.outdir)
metafos = {}
if args.multiplicity_column is None:  # if not set, read abundances from args.abundance_basename
    with open('%s/%s'%(args.gctreedir, args.abundance_basename)) as afile:
        reader = csv.DictReader(afile, fieldnames=('name', 'abundance'))
        for line in reader:
            if line['name'] not in metafos:
                line['name'] = {}
            metafos[line['name']]['multiplicity'] = max(1, int(line['abundance']))  # increase 0s (inferred ancestors) to 1
if args.kdfname is not None:
    with open(args.kdfname) as kfile:
        reader = csv.DictReader(kfile)
        for line in reader:
            uid = line[args.name_column]
            kdval = 0
            for kdc in args.kd_columns:
                kdval += float(line[kdc])
            if uid not in metafos:
                metafos[uid] = {}
            metafos[uid]['affinity'] = kdval if args.dont_invert_kd else 1. / kdval
            if args.multiplicity_column is not None:
                metafos[uid]['multiplicity'] = int(line[args.multiplicity_column])

# convert metafos to per-locus names
for base_id in metafos.keys():
    for ltmp in utils.sub_loci('ig'):
        new_id = '%s-%s' % (base_id, ltmp)
        metafos[new_id] = metafos[base_id]
    del metafos[base_id]
# and write to json/yaml
with open(metafname(), 'w') as mfile:
    json.dump(metafos, mfile)

for action in args.actions:
    run_cmd(action)
