#!/usr/bin/env python
import sys
import csv
csv.field_size_limit(sys.maxsize)  # make sure we can write very large csv fields
import os
import argparse
import colored_traceback.always
import glob
import itertools

# if you move this script, you'll need to change this method of getting the imports
partis_dir = os.path.dirname(os.path.realpath(__file__)).replace('/projects', '')
sys.path.insert(1, partis_dir + '/python')

import utils
import glutils

mdir = 'packages/MobiLLe/Data/Simulated_datasets'
base_odir = '/fh/fast/matsen_e/dralph/partis/mobille-validation'
vsn = 'v0'

# ----------------------------------------------------------------------------------------
def get_true_ptn(scode, stype):
    tcfn = '%s/True_cluster_by_simulator/%s_%s_true_cluster.txt' % (mdir, scode, stype)
    true_partition = []
    with open(tcfn) as tcfile:
        reader = csv.DictReader(tcfile, delimiter='\t', fieldnames=['iclust', 'uids'])
        for line in reader:
            cluster = [u.strip() for u in line['uids'].split()]
            true_partition.append(cluster)
    return true_partition

# ----------------------------------------------------------------------------------------
def bodir(scode, stype):
    return '%s/%s/%s-%s' % (base_odir, vsn, scode, stype)

# ----------------------------------------------------------------------------------------
def paramdir(scode, stype):
    return '%s/parameters' % bodir(scode, stype)

# ----------------------------------------------------------------------------------------
def ps_ofn(scode, stype):
    return '%s/%s/%s-%s/partition.yaml' % (base_odir, vsn, scode, stype)
# ----------------------------------------------------------------------------------------
def pltdir(scode, stype):
    return '%s/plots' % bodir(scode, stype)

# ----------------------------------------------------------------------------------------
def mb_metrics(mtype, inf_ptn, tru_ptn, debug=True):
    # ----------------------------------------------------------------------------------------
    def id_dict(ptn):
        reco_info = utils.build_dummy_reco_info(ptn)  # not actually reco info unless it's the true partition
        return {uid : reco_info[uid]['reco_id'] for cluster in ptn for uid in cluster}  # speed optimization
    # ----------------------------------------------------------------------------------------
    utils.check_intersection_and_complement(inf_ptn, tru_ptn, a_label='true', b_label='inferred')
    if mtype == 'pairwise':
        tp, fp, fn, n_tot = 0, 0, 0, 0
        tru_ids, inf_ids = [id_dict(ptn) for ptn in [tru_ptn, inf_ptn]]
        for u1, u2 in itertools.combinations(set(u for c in tru_ptn for u in c), 2):
            is_tru_clonal, is_inf_clonal = [tids[u1] == tids[u2] for tids in [tru_ids, inf_ids]]
            n_tot += 1
            if is_tru_clonal and is_inf_clonal:
                tp += 1
            elif is_tru_clonal:
                fn += 1
            elif is_inf_clonal:
                fp += 1
            else:  # singletons
                pass
        precis = tp / float(tp + fp)
        recall = tp / float(tp + fn)
        return precis, recall, 2 * precis * recall / float(precis + recall)
    elif mtype == 'closeness':
        pass
    else:
        assert False

# ----------------------------------------------------------------------------------------
def run_partis(seqfn, scode, stype):
    ofn = ps_ofn(scode, stype)
    if os.path.exists(ofn):
        print '    %s %s partis output exists: %s' % (scode, stype, ofn)
        return
    for action in ['cache-parameters', 'partition']:
        cmd = './bin/partis %s --infname %s --parameter-dir %s' % (action, seqfn, paramdir(scode, stype))
        if action == 'partition':
            cmd += ' --outfname %s' % ofn
        utils.simplerun(cmd, logfname=utils.replace_suffix(ofn, '.log')) #, dryrun=True)

# ----------------------------------------------------------------------------------------
for fn in glob.glob('%s/Fasta/*.fasta'%mdir):
    scode, stype, tstr = utils.getprefix(os.path.basename(fn)).split('_')  # e.g. l0046 oligo
# ----------------------------------------------------------------------------------------
    if stype != 'mono' or scode != 'l0046':
        continue
    assert tstr == 'simulated'
    run_partis(fn, scode, stype)

    true_partition = get_true_ptn(scode, stype)
    _, _, cpath = utils.read_output(ps_ofn(scode, stype))
    inf_ptn = cpath.best()
    print mb_metrics('pairwise', inf_ptn, true_partition)
    # print utils.per_seq_correct_cluster_fractions(inf_ptn, true_partition, debug=True)
    # import plotting
    # plotting.plot_cluster_similarity_matrix(pltdir(scode, stype), 'csim-matrix', 'true', true_partition, 'partis', inf_ptn, 30) #, debug=True)
    # sys.exit()
