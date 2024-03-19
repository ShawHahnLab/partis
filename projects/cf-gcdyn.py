#!/usr/bin/env python3
from __future__ import absolute_import, division, unicode_literals
from __future__ import print_function
import argparse
import os
import sys
import colored_traceback.always
import numpy
import math
import collections
import multiprocessing
import glob
import copy

partis_dir = os.path.dirname(os.path.realpath(__file__)).replace('/projects', '')
sys.path.insert(1, partis_dir) # + '/python')
import python.utils as utils
import python.paircluster as paircluster
import python.scanplot as scanplot
import python.plotting as plotting
import python.clusterpath as clusterpath

# ----------------------------------------------------------------------------------------
# This is the template/minimal implementation (not necessarily functional) for scan scripts, final versions of which include test/{cf-{germline-inference,paired-loci,tree-metrics}.py and projects/cf-gcdyn.py
# Each of those scripts run most of the steps for a paper, and they (roughly speaking) run a bunch of different methods/metrics and compare the results while scanning over a bunch of different variables.
# No real documentation, although help msgs are there.

# ----------------------------------------------------------------------------------------
script_base = os.path.basename(__file__).replace('cf-', '').replace('.py', '')
dl_metrics = ['%s-%s-%s' % (p, s, m) for s in ['train', 'test'] for m in ['bias', 'variance', 'mae'] for p in ['xscale', 'xshift']] + ['xscale-train-vs-test-mae']
all_perf_metrics = ['max-abundances', 'distr-abundances', 'distr-hdists', 'all-dl', 'all-test-dl'] + dl_metrics #'precision', 'sensitivity', 'f1', 'time-reqd', 'naive-hdist', 'cln-frac']  # pcfrac-*: pair info cleaning correct fraction, cln-frac: collision fraction
after_actions = ['merge-simu', 'replay-plot', 'dl-infer', 'dl-infer-merged', 'partis']  # actions that come after simulation (e.g. partition)
plot_actions = ['group-expts']  # these are any actions that don't require running any new action, and instead are just plotting stuff that was run by a previous action (e.g. single-chain-partis in cf-paired-loci) (note, does not include 'plot' or 'combine-plots')
merge_actions = ['merge-simu', 'dl-infer-merged']  # actions that act on all scanned values at once (i.e. only run once, regardless of how many scan vars/values)

# ----------------------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--actions', default='don\'t use')  # old defaults: simu:merge-simu:process:plot (partis is just to make tree plots, which aren't really slow but otoh we don't need for every seed/variable combo)
parser.add_argument('--birth-response-list')
parser.add_argument('--xscale-values-list')
parser.add_argument('--xshift-values-list')
parser.add_argument('--xscale-range-list')
parser.add_argument('--xshift-range-list')
parser.add_argument('--yscale-range-list')
parser.add_argument('--initial-birth-rate-range-list')
parser.add_argument('--carry-cap-range-list')
parser.add_argument('--time-to-sampling-range-list')
parser.add_argument('--n-seqs-range-list')
parser.add_argument('--n-trials-list')
parser.add_argument('--dl-bundle-size-list', help='size of bundles during dl inference (must be equal to or less than simulation bundle size)')
parser.add_argument('--epochs-list')
parser.add_argument('--dropout-rate-list')
parser.add_argument('--learning-rate-list')
parser.add_argument('--ema-momentum-list')
parser.add_argument('--prebundle-layer-cfg-list')
parser.add_argument('--dont-scale-params-list')
parser.add_argument('--params-to-predict-list')
parser.add_argument('--n-trees-per-expt-list', help='Number of per-tree predictions to group together and average over during the \'group-expts\' action (see also --dl-bundle-size-list)')
parser.add_argument('--simu-bundle-size-list', help='Number of trees to simulate with each chosen set of parameter values, in each simulation subprocess (see also --n-trees-per-expt-list')
parser.add_argument('--data-samples-list', help='List of data samples to run on. Don\'t set this, it uses glob on --data-dir')
utils.add_scanvar_args(parser, script_base, all_perf_metrics, default_plot_metric='replay-plot')
parser.add_argument('--dl-extra-args')
parser.add_argument('--gcddir', default='%s/work/partis/projects/gcdyn'%os.getenv('HOME'))
# parser.add_argument('--gcreplay-data-dir', default='/fh/fast/matsen_e/%s/gcdyn/gcreplay-observed'%os.getenv('USER'))
parser.add_argument('--gcreplay-germline-dir', default='datascripts/meta/taraki-gctree-2021-10/germlines')
parser.add_argument('--dl-model-dir')
parser.add_argument('--data-dir', default='/fh/fast/matsen_e/data/taraki-gctree-2021-10/beast-processed-data/v0')
args = parser.parse_args()
args.scan_vars = {
    'simu' : ['seed', 'birth-response', 'xscale-values', 'xshift-values', 'xscale-range', 'xshift-range', 'yscale-range', 'initial-birth-rate-range', 'carry-cap-range', 'time-to-sampling-range', 'n-seqs-range', 'n-trials', 'simu-bundle-size'],
    'dl-infer' : ['dl-bundle-size', 'epochs', 'dropout-rate', 'learning-rate', 'ema-momentum', 'prebundle-layer-cfg', 'dont-scale-params', 'params-to-predict'],
    'data' : ['data-samples'],
}
args.scan_vars['group-expts'] = copy.deepcopy(args.scan_vars['dl-infer'])
args.str_list_vars = ['xscale-values', 'xshift-values', 'xscale-range', 'xshift-range', 'yscale-range', 'initial-birth-rate-range', 'time-to-sampling-range', 'carry-cap-range', 'n-seqs-range', 'params-to-predict']  #  scan vars that are colon-separated lists (e.g. allowed-cdr3-lengths)
args.recurse_replace_vars = []  # scan vars that require weird more complex parsing (e.g. allowed-cdr3-lengths, see cf-paired-loci.py)
args.bool_args = ['dont-scale-params']  # need to keep track of bool args separately (see utils.add_to_scan_cmd())
if 'data' in args.actions:
    args.data_samples_list = ':'.join(os.path.basename(d) for d in glob.glob('%s/*' % args.data_dir))
    print('  running on %d data samples from %s' % (len(args.data_samples_list), args.data_dir))
utils.process_scanvar_args(args, after_actions, plot_actions, all_perf_metrics)
if args.inference_extra_args is not None:
    raise Exception('not used atm')
if 'all-dl' in args.perf_metrics:
    args.perf_metrics += dl_metrics
    args.perf_metrics.remove('all-dl')
if 'all-test-dl' in args.perf_metrics:
    args.perf_metrics += [m for m in dl_metrics if 'test' in m]
    args.perf_metrics.remove('all-test-dl')
if 'group-expts' in args.plot_metrics and any('train' in m for m in args.perf_metrics):
    acts_to_remove = [m for m in args.perf_metrics if 'train' in m]
    print('    can\'t plot any training metrics for \'group-expts\' so removing: %s' % ' '.join(acts_to_remove))
    args.perf_metrics = [m for m in args.perf_metrics if 'train' not in m]
if args.params_to_predict_list is not None:
    before_metrics = copy.copy(args.perf_metrics)
    args.perf_metrics = [m for m in args.perf_metrics if any(p in m for plist in args.params_to_predict_list for p in plist)]
    print('    restricting perf metrics to correspond to --params-to-predict (removed %s)' % (' '.join(m for m in before_metrics if m not in args.perf_metrics)))

# ----------------------------------------------------------------------------------------
def odir(args, varnames, vstrs, action):
    return utils.svoutdir(args, varnames, vstrs, action)

# ----------------------------------------------------------------------------------------
def ofname(args, varnames, vstrs, action, ftype='npy'):
    if action == 'merge-simu':
        varnames = []
        vstrs = []
    if action in ['simu', 'merge-simu']:
        ftstrs = {  # copied from gcdyn/scripts/multi_simulation.py
            'fasta' : 'seqs',
            'nwk' : 'trees',
            'npy' : 'encoded-trees',
            'pkl' : 'responses',
        }
        sfx = '%s.%s' % (ftstrs.get(ftype, 'simu'), ftype)
    elif action == 'replay-plot':
        sfx = 'diff-vals.yaml'
    elif action in ['dl-infer', 'dl-infer-merged', 'group-expts']:
        sfx = 'test.csv'
    elif action == 'partis':
        sfx = 'partition.yaml'
    elif action == 'data':
        sfx = 'infer.csv'
    else:
        assert False
    return '%s/%s/%s' % (odir(args, varnames, vstrs, action), action, sfx)

# ----------------------------------------------------------------------------------------
def add_mamba_cmds(cmd):
    cmd = utils.mamba_cmds('gcdyn') + [cmd]
    cmd = ' && '.join(cmd)
    return cmd

# ----------------------------------------------------------------------------------------
def get_cmd(action, base_args, varnames, vlists, vstrs, all_simdirs=None):
    # ----------------------------------------------------------------------------------------
    def add_scan_args(cmd, skip_fcn=None):  # using nargs='+' syntax for these rather than partis-style colons
        for barg in base_args:  # NOTE don't modify base_args here
            bname, bstr = barg.replace('--', '').split(' ')  # barg is both arg and val e.g. '--arg val'
            if skip_fcn is not None and skip_fcn(bname):
                continue
            if bname in args.str_list_vars:
                bstr = bstr.replace(':', ' ')
            cmd += ' --%s %s' % (bname, bstr)
        for vname, vstr in zip(varnames, vstrs):
            if skip_fcn is not None and skip_fcn(vname):
                continue
            if vname in args.str_list_vars:
                vstr = vstr.replace(':', ' ')
            cmd = utils.add_to_scan_cmd(args, vname, vstr, cmd)
        return cmd
    # ----------------------------------------------------------------------------------------
    if action in ['simu', 'merge-simu']:
        cmd = 'gcd-simulate' if action=='simu' else 'python %s/scripts/%s.py' % (args.gcddir, 'combine-simu-files.py')
        if action == 'simu':
            cmd += ' --outdir %s' % os.path.dirname(ofname(args, varnames, vstrs, action))  #  --debug 1
            if args.test:
                cmd += ' --test'
            cmd = add_scan_args(cmd)
        else:
            cmd += ' %s --outdir %s' % (' '.join(all_simdirs), os.path.dirname(ofname(args, [], [], action)))
        if args.n_sub_procs > 1:
            cmd += ' --n-sub-procs %d' % args.n_sub_procs
        if action == 'simu' and args.simu_extra_args is not None:
            cmd += ' %s' % args.simu_extra_args
        cmd = add_mamba_cmds(cmd)
    elif action == 'replay-plot':
        cmd = './projects/replay-plot.py --simu-dir %s --outdir %s' % (os.path.dirname(ofname(args, varnames, vstrs, 'simu')), os.path.dirname(ofname(args, varnames, vstrs, action)))
    elif action in ['dl-infer', 'dl-infer-merged', 'group-expts']:
        if 'dl-infer' in action:  # could be 'dl-infer' or 'dl-infer-merged'
            cmd = 'gcd-dl %s --is-simu --indir %s --outdir %s' % ('train' if args.dl_model_dir is None else 'infer', os.path.dirname(ofname(args, varnames, vstrs, 'merge-simu' if action=='dl-infer-merged' else 'simu', ftype='npy')), os.path.dirname(ofname(args, varnames, vstrs, action)))
            if args.dl_extra_args is not None:
                cmd += ' %s' % args.dl_extra_args
            if args.dl_model_dir is not None:
                cmd += ' --model-dir %s' % args.dl_model_dir
        else:
            cmd = 'python %s/scripts/group-gcdyn-expts.py --indir %s --outdir %s' % (args.gcddir, os.path.dirname(ofname(args, varnames, vstrs, 'dl-infer')), os.path.dirname(ofname(args, varnames, vstrs, action)))
            cmd = add_mamba_cmds(cmd)
        cmd = add_scan_args(cmd, skip_fcn=lambda vname: vname in args.scan_vars['simu'] or vname not in args.scan_vars[action] or action=='group-expts' and vname in args.scan_vars['dl-infer'])  # ick
    elif action == 'partis':
        # make a partition-only file
        simdir = os.path.dirname(ofname(args, varnames, vstrs, 'simu'))
        ptnfn = '%s/true-partition.yaml' % simdir
        if not os.path.exists(ptnfn):
            print('    writing true partitions: %s' % ptnfn)
            all_seqs = [s['name'] for s in utils.read_fastx(ofname(args, varnames, vstrs, 'simu'))]  # just to make sure we get the names right
            true_partition = []
            for sfn in glob.glob('%s/seqs_*.fasta'%simdir):
                sfos = utils.read_fastx(sfn)
                icluster = int(os.path.basename(sfn).replace('seqs_', '').replace('.fasta', ''))
                true_partition.append(['%d-%s' % (icluster, s['name']) for s in sfos])
            utils.write_annotations(ptnfn, None, [], utils.annotation_headers, partition_lines=clusterpath.ClusterPath(partition=true_partition).get_partition_lines())
        # then get command
        odir = '%s' % os.path.dirname(ofname(args, varnames, vstrs, action))
        cmd = './bin/partis partition --species mouse --infname %s --input-partition-fname %s --treefname %s --parameter-dir %s/parameters --outfname %s' % (ofname(args, varnames, vstrs, 'simu'), ptnfn, ofname(args, varnames, vstrs, 'simu', trees=True), odir, ofname(args, varnames, vstrs, action))
        cmd += ' --initial-germline-dir %s --no-insertions-or-deletions --min-selection-metric-cluster-size 3' % args.gcreplay_germline_dir
        cmd += ' --plotdir %s/plots --partition-plot-cfg trees' % odir
        # if args.inference_extra_args is not None:
        #     cmd += ' %s' % args.inference_extra_args
    elif action == 'data':
        odir = os.path.dirname(ofname(args, varnames, vstrs, action))
        assert len(vstrs) == 1  # should just one data sample in a list
        smpl = vstrs[0]
        cmd = 'gcd-dl infer --model-dir %s --indir %s/%s --outdir %s' % (args.dl_model_dir, args.data_dir, smpl, odir)
        if args.dl_bundle_size_list is not None:  # kind of weird to use it for this as well as a scan var, but whatever
            assert len(args.dl_bundle_size_list) == 1
            cmd += ' --dl-bundle-size %d' % int(args.dl_bundle_size_list[0])
    else:
        assert False
    return cmd

# ----------------------------------------------------------------------------------------
# would be nice to combine this also with fcns in cf-tree-metrics.py (and put it in scanplot)
def run_scan(action):
    # ----------------------------------------------------------------------------------------
    def init_cmd(local_varnames, vstrs, ofn, icombo):
        cmd = get_cmd(action, base_args, local_varnames, val_lists, vstrs, all_simdirs=all_simdirs)
        # utils.simplerun(cmd, logfname='%s-%s.log'%(odir(args, local_varnames, vstrs, action), action), dryrun=args.dry)
        cmdfos.append({
            'cmd_str' : cmd,
            'outfname' : ofn,
            'logdir' : odir(args, local_varnames, vstrs, action),
            'workdir' : '%s/partis-work/%d' % (args.workdir, icombo),
        })
    # ----------------------------------------------------------------------------------------
    base_args, varnames, val_lists, valstrs = utils.get_var_info(args, args.scan_vars[action])
    cmdfos = []
    print('  %s: running %d combinations of: %s' % (utils.color('blue_bkg', action), len(valstrs), ' '.join(varnames)))
    if args.debug:
        print('   %s' % ' '.join(varnames))
    n_already_there, n_missing_input, ifn = 0, 0, None
    all_simdirs = []
    for icombo, vstrs in enumerate(valstrs):
        if args.debug:
            print('   %s' % ' '.join(vstrs))

        ofn = ofname(args, varnames, vstrs, action) if action not in merge_actions else ofname(args, [], [], action)  #, single_file=True)
        if utils.output_exists(args, ofn, debug=False):
            n_already_there += 1
            continue

        if action in ['replay-plot'] + merge_actions:
            ifn = ofname(args, varnames, vstrs, 'simu')
            if not os.path.exists(ifn):  # do *not* use this, it'll delete it if --overwrite is set: utils.output_exists(args, ifn, debug=False):
                n_missing_input += 1
                continue
            if action in merge_actions:
                all_simdirs.append(os.path.dirname(ifn))
                continue

        init_cmd(varnames, vstrs, ofn, icombo)

    if action in merge_actions and len(all_simdirs) > 0:
        if action == 'merge-simu' and n_missing_input > 0:
            print('    %s writing merged simulation file despite missing some of its input files' % utils.wrnstr())
        init_cmd([], [], ofn, 0)

    utils.run_scan_cmds(args, cmdfos, '%s.log'%action, len(valstrs), n_already_there, ofn, n_missing_input=n_missing_input, single_ifn=ifn, shell=any('micromamba activate' in c['cmd_str'] for c in cmdfos))

# ----------------------------------------------------------------------------------------
def get_fnfcn(method, pmetr):  # have to adjust signature before passing to fcn in scavars
    def tmpfcn(varnames, vstrs): return ofname(args, varnames, vstrs, method)
    return tmpfcn

# ----------------------------------------------------------------------------------------
import random
random.seed(args.random_seed)
numpy.random.seed(args.random_seed)
if args.workdir is None:
    args.workdir = utils.choose_random_subdir('/tmp/%s/hmms' % (os.getenv('USER', default='partis-work')))

for action in args.actions:
    if action in ['simu', 'data', ] + after_actions + plot_actions:
        run_scan(action)
    elif action in ['plot', 'combine-plots']:
        plt_scn_vars = args.scan_vars['group-expts']
        if args.dry:
            print('  --dry: not plotting')
            continue
        _, varnames, val_lists, valstrs = utils.get_var_info(args, plt_scn_vars)
        if action == 'plot':
            print('plotting %d combinations of %d variable%s (%s) to %s' % (len(valstrs), len(varnames), utils.plural(len(varnames)), ', '.join(varnames), scanplot.get_comparison_plotdir(args, None)))
            fnames = {meth : {pmetr : [] for pmetr in args.perf_metrics} for meth in args.plot_metrics}
            procs = []
            for method in args.plot_metrics:
                for pmetr in args.perf_metrics:
                    utils.prep_dir(scanplot.get_comparison_plotdir(args, method) + '/' + pmetr, wildlings=['*.html', '*.svg', '*.yaml'])  # , subdirs=args.perf_metrics
                for pmetr in args.perf_metrics:
                    print('  %12s %s' % (method, pmetr))
                    arglist, kwargs = (args, plt_scn_vars, action, method, pmetr, args.final_plot_xvar), {'fnfcn' : get_fnfcn(method, pmetr), 'fnames' : fnames[method][pmetr], 'script_base' : script_base, 'debug' : args.debug}
                    if args.test:
                        scanplot.make_plots(*arglist, **kwargs)
                    else:
                        procs.append(multiprocessing.Process(target=scanplot.make_plots, args=arglist, kwargs=kwargs))
            if not args.test:
                utils.run_proc_functions(procs)
            for method in args.plot_metrics:
                for pmetr in args.perf_metrics:
                    pmcdir = scanplot.get_comparison_plotdir(args, method) + '/' + pmetr
                    fnames[method][pmetr] = [[f.replace(pmcdir+'/', '') for f in fnames[method][pmetr]]]
                    plotting.make_html(pmcdir, n_columns=3, fnames=fnames[method][pmetr])  # this doesn't work unless --test is set since multiprocessing uses copies of <fnames>, but whatever, just run combine-plots
        elif action == 'combine-plots':
            cfpdir = scanplot.get_comparison_plotdir(args, 'combined')
            utils.prep_dir(cfpdir, wildlings=['*.html', '*.svg'])
            fnames = [[] for _ in args.perf_metrics]
            for ipm, pmetr in enumerate(args.perf_metrics):
                print('    ', pmetr)
                scanplot.make_plots(args, plt_scn_vars, action, None, pmetr, args.final_plot_xvar, fnames=fnames[ipm], make_legend=True, debug=args.debug)
            plotting.make_html(cfpdir, fnames=fnames)
        else:
            raise Exception('unsupported action %s' % action)
    else:
        raise Exception('unsupported action %s' % action)
