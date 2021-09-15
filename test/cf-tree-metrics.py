#!/usr/bin/env python
import argparse
import operator
import os
import sys
import yaml
import json
import colored_traceback.always
import collections
import numpy
import math
import subprocess
import multiprocessing
import copy

# ----------------------------------------------------------------------------------------
linestyles = {'lbi' : '-', 'lbr' : '-', 'dtr' : '--'}
linewidths = {'lbi' : 2.5, 'lbr' : 2.5, 'dtr' : 3}
hard_colors = {'dtr' : '#626262',
               'aa-lbi' : '#e043b9',
               'aa-lbr' : '#e043b9'}  # don't like the cycle colors these end up with
def metric_color(metric):  # as a fcn to avoid import if we're not plotting
    if metric in hard_colors:
        return hard_colors[metric]
    mstrlist = ['shm:lbi:cons-dist-aa:cons-dist-nuc:dtr:aa-lbi', 'delta-lbi:lbr:dtr:aa-lbr']
    metric_colors = {m : plotting.frozen_pltcolors[i % len(plotting.frozen_pltcolors)] for mstrs in mstrlist for i, m in enumerate(mstrs.split(':'))}
    return metric_colors.get(metric, 'red')

# ----------------------------------------------------------------------------------------
def ura_vals(xvar):  # list of whether we're using relative affinity values
    if xvar == 'affinity' and args.include_relative_affy_plots:
        return [False, True]  # i.e. [don'e use relative affy, do use relative affy]
    else:
        return [False]
# ----------------------------------------------------------------------------------------
def get_n_generations(ntl, tau):  # NOTE duplicates code in treeutils.calculate_max_lbi()
    return max(1, int(args.seq_len * tau * ntl))

# ----------------------------------------------------------------------------------------
def get_outfname(outdir):
    return '%s/vals.yaml' % outdir

# ----------------------------------------------------------------------------------------
def make_lb_bound_plots(args, outdir, metric, btype, parsed_info, print_results=False):
    def make_plot(log, parsed_info):
        fig, ax = plotting.mpl_init()
        for lbt in sorted(parsed_info[metric][btype], reverse=True):
            n_gen_list, lb_list = zip(*sorted(parsed_info[metric][btype][lbt].items(), key=operator.itemgetter(0)))
            if lbt == 1. / args.seq_len:  # add a horizontal line corresponding to the asymptote for tau = 1/seq_len
                ax.plot(ax.get_xlim(), (lb_list[-1], lb_list[-1]), linewidth=3, alpha=0.7, color='darkred', linestyle='--') #, label='1/seq len')
            ax.plot(n_gen_list, lb_list, label='%.4f' % lbt, alpha=0.7, linewidth=4)
            if print_results and log == '':
                print '      %7.4f    %6.4f' % (lbt, lb_list[-1])
        plotname = 'tau-vs-n-gen-vs-%s-%s' % (btype, metric)
        if log == '':
            ybounds = None
            leg_loc = (0.1, 0.5)
        else:
            plotname += '-log'
            if metric == 'lbi':
                ybounds = (2*min(parsed_info[metric][btype]), 3*ax.get_ylim()[1])
            else:
                ybounds = None
            leg_loc = (0.04, 0.57)
        plotting.mpl_finish(ax, outdir, plotname, log=log, xbounds=(min(n_gen_list), max(n_gen_list)), ybounds=ybounds,
                            xlabel='N generations', ylabel='%s %s' % (btype.capitalize(), metric.upper()), leg_title='tau', leg_prop={'size' : 12}, leg_loc=leg_loc)

    if print_results:
        print '%s:     tau    %s %s' % (btype, btype, metric)

    for log in ['', 'y']:
        make_plot(log, parsed_info)

# ----------------------------------------------------------------------------------------
def calc_lb_bounds(args, n_max_gen_to_plot=4, lbt_bounds=(0.001, 0.005), print_results=False):
    print_results = True
    btypes = ['min', 'max']

    outdir = '%s/lb-tau-normalization/%s' % (args.base_outdir, args.label)

    parsed_info = {m : {b : {} for b in btypes} for m in args.only_metrics}
    for lbt in args.lb_tau_list:
        if args.make_plots and (lbt < lbt_bounds[0] or lbt > lbt_bounds[1]):
            print '    skipping tau %.4f outside of bounds [%.4f, %.4f] for bound plotting' % (lbt, lbt_bounds[0], lbt_bounds[1])
            continue

        gen_list = args.n_generations_list
        if gen_list is None:
            gen_list = [get_n_generations(ntl, lbt) for ntl in args.n_tau_lengths_list]
        if args.lb_tau_list.index(lbt) == 0 or args.n_tau_lengths_list is not None:  # if --n-tau-lengths-list is set, they could be different for each tau
            print ' seq len: %d   N gen list: %s' % (args.seq_len, ' '.join(str(n) for n in gen_list))
        print '   %s %.4f' % (utils.color('green', 'lb tau'), lbt)
        for n_gen in gen_list:
            if args.debug:
                print '     %s %d  %s %.4f' % (utils.color('purple', 'N gen'), n_gen, utils.color('purple', 'lb tau'), lbt)

            this_outdir = '%s/n_gen-%d-lbt-%.4f' % (outdir, n_gen, lbt)  # if for some reason I want to specify --n-tau-lengths-list instead of --n-generations-list, this makes the output path structure still correspond to n generations, but that's ok since that's what the trees do

            if args.make_plots:  # just let it crash if you forgot to actually run it first
                with open(get_outfname(this_outdir)) as outfile:
                    info = yaml.load(outfile, Loader=yaml.Loader)
                for metric in args.only_metrics:
                    for btype in btypes:
                        if lbt not in parsed_info[metric][btype]:
                            parsed_info[metric][btype][lbt] = {}
                        parsed_info[metric][btype][lbt][n_gen] = info[metric][btype][metric]  # it's weird to have metric as the key twice, but it actually makes sense since we're subverting the normal calculation infrastructure to only run one metric or the other at a time (i.e. the righthand key is pulling out the metric we want from the lb info that, in principle, usually has both; while the lefthand key is identifying a run during which we were only caring about that metric)
                continue
            elif utils.output_exists(args, get_outfname(this_outdir)):
                continue

            print '         running n gen %d' % n_gen

            if not os.path.exists(this_outdir):
                os.makedirs(this_outdir)

            lbvals = treeutils.calculate_lb_bounds(args.seq_len, lbt, n_generations=n_gen, n_offspring=args.max_lb_n_offspring, only_metrics=args.only_metrics, btypes=btypes, debug=args.debug)

            with open(get_outfname(this_outdir), 'w') as outfile:
                yamlfo = {m : {b : {k : v for k, v in lbvals[m][b].items() if k != 'vals'} for b in btypes} for m in args.only_metrics}  # writing these to yaml is really slow, and they're only used for plotting below
                yaml.dump(yamlfo, outfile)

            if n_gen > n_max_gen_to_plot:
                continue

            # this is really slow on large trees
            plotdir = this_outdir + '/plots'
            utils.prep_dir(plotdir, wildlings='*.svg')
            for metric in args.only_metrics:
                for btype in btypes:
                    if lbvals[metric][btype]['vals'] is None:
                        continue
                    cmdfos = [lbplotting.get_lb_tree_cmd(lbvals[metric][btype]['vals']['tree'], '%s/%s-%s-tree.svg' % (plotdir, metric, btype), metric, 'affinities', args.ete_path, args.workdir, metafo=lbvals[metric][btype]['vals'], tree_style='circular')]
                    utils.run_cmds(cmdfos, clean_on_success=True, shell=True, debug='print')

    if args.make_plots:
        print '  writing plots to %s' % outdir
        for metric in args.only_metrics:
            for btype in btypes:
                if 'lbr' in metric and btype == 'min':  # it's just zero, and confuses the log plots
                    continue
                if len(parsed_info[metric][btype]) == 0:
                    print 'nothing to do (<parsed_info> empty)'
                    continue
                make_lb_bound_plots(args, outdir, metric, btype, parsed_info, print_results=print_results)

# ----------------------------------------------------------------------------------------
def get_bcr_phylo_outdir(varnames, vstr):
    return utils.svoutdir(args, varnames, vstr, 'simu') + '/bcr-phylo'

# ----------------------------------------------------------------------------------------
def get_simfname(varnames, vstr):
    return '%s/selection/simu/mutated-simu.yaml' % get_bcr_phylo_outdir(varnames, vstr)

# ----------------------------------------------------------------------------------------
def get_parameter_dir(varnames, vstr):
    return '%s/selection/partis/params' % get_bcr_phylo_outdir(varnames, vstr)

# ----------------------------------------------------------------------------------------
def get_tree_metric_outdir(varnames, vstr, metric_method=None):  # metric_method is only set if it's neither lbi nor lbr
    return utils.svoutdir(args, varnames, vstr, 'get-tree-metrics') + '/' + ('partis' if metric_method is None else metric_method)

# ----------------------------------------------------------------------------------------
def get_partition_fname(varnames, vstr, action, metric_method=None):  # if action is 'bcr-phylo', we want the original partition output file, but if it's 'get-tree-metrics', we want the copied one, that had tree metrics added to it (and which is in the e.g. tau subdir) UPDATE no longer modifying output files by default, so no longer doing the copying thing
    if action == 'bcr-phylo' or metric_method is not None:  # for non-lb metrics (i.e. if metric_method is set) we won't modify the partition file, so can just read the one in the bcr-phylo dir
        outdir = '%s/selection/partis' % get_bcr_phylo_outdir(varnames, vstr)
    else:
        outdir = get_tree_metric_outdir(varnames, vstr)
    return '%s/partition.yaml' % outdir

# ----------------------------------------------------------------------------------------
def get_tree_metric_plotdir(varnames, vstr, metric_method=None, extra_str=''):
    return  '%s/%splots' % (get_tree_metric_outdir(varnames, vstr, metric_method=metric_method), extra_str+'-' if extra_str != '' else '')

# ----------------------------------------------------------------------------------------
def get_dtr_model_dir(varnames, vstr, extra_str=''):
    plotdir = get_tree_metric_plotdir(varnames, vstr, metric_method='dtr', extra_str=extra_str)
    if plotdir.split('/')[-1] == 'plots':
        assert extra_str == ''  # i think?
        delim = '/'
    elif plotdir.split('-')[-1] == 'plots':  # i.e. args.extra_plotstr was set when we trained
        assert extra_str != ''  # i think?
        delim = '-'
    else:
        assert False
    plstr = delim + 'plots'
    assert plotdir.count(plstr) == 1
    return plotdir.replace(plstr, delim + 'dtr-models')

# ----------------------------------------------------------------------------------------
def rel_affy_str(use_relative_affy, metric):
    return '-relative' if use_relative_affy and metric == 'lbi' else ''

# ----------------------------------------------------------------------------------------
def get_tm_fname(varnames, vstr, metric, x_axis_label, use_relative_affy=False, cg=None, tv=None, extra_str=''):  # note that there are separate svg files for each iclust, but info for all clusters are written to the same yaml file (but split apart with separate info for each cluster)
    if metric == 'dtr':
        assert cg is not None and tv is not None
    if metric in ['lbi', 'lbr']:  # NOTE using <metric> and <metric_method> for slightly different but overlapping things: former is the actual metric name, whereas setting the latter says we want a non-lb metric (necessary because by default we want to calculate lbi and lbr, but also be able treat lbi and lbr separately when plotting)
        plotdir = get_tree_metric_plotdir(varnames, vstr, extra_str=extra_str)
        old_path = '%s/true-tree-metrics/%s-vs-%s-true-tree-ptiles%s.yaml' % (plotdir, metric, x_axis_label, rel_affy_str(use_relative_affy, metric))  # just for backwards compatibility, could probably remove at some point (note: not updating this when I'm adding non-lb metrics like shm)
        if os.path.exists(old_path):
            return old_path
    else:
        plotdir = get_tree_metric_plotdir(varnames, vstr, metric_method=metric, extra_str=extra_str)
    return treeutils.tmfname(plotdir, metric, x_axis_label, cg=cg, tv=tv, use_relative_affy=use_relative_affy)

# ----------------------------------------------------------------------------------------
def get_all_tm_fnames(varnames, vstr, metric_method=None, extra_str=''):
    if metric_method is None:
        return [get_tm_fname(varnames, vstr, mtmp, xatmp, use_relative_affy=use_relative_affy, extra_str=extra_str)
                for mtmp, cfglist in lbplotting.lb_metric_axis_cfg(args.metric_method)
                for xatmp, _ in cfglist
                for use_relative_affy in ura_vals(xatmp)]  # arg wow that's kind of complicated and ugly
    elif metric_method == 'dtr':
        if args.train_dtr:  # training
            return [treeutils.dtrfname(get_dtr_model_dir(varnames, vstr, extra_str=extra_str), cg, tvar) for cg in treeutils.cgroups for tvar in treeutils.dtr_targets[cg]]
        else:  # testing
            return [get_tm_fname(varnames, vstr, metric_method, lbplotting.getptvar(tv), cg=cg, tv=tv, use_relative_affy=use_relative_affy, extra_str=extra_str) for cg in treeutils.cgroups for tv in treeutils.dtr_targets[cg] for use_relative_affy in ura_vals(tv)]
    else:
        return [get_tm_fname(varnames, vstr, metric_method, 'n-ancestor' if metric_method in ['delta-lbi', 'lbr', 'aa-lbr'] else 'affinity', extra_str=extra_str)]  # this hard coding sucks, and it has to match some stuff in treeutils.calculate_non_lb_tree_metrics()

# ----------------------------------------------------------------------------------------
def get_comparison_plotdir(metric, per_x, extra_str=''):  # both <metric> and <per_x> can be None, in which case we return the parent dir
    plotdir = '%s/%s/plots' % (args.base_outdir, args.label)
    if metric is not None:
        plotdir += '/' + metric
        if metric == 'combined' and args.combo_extra_str is not None:
            plotdir += '-' + args.combo_extra_str
    if extra_str != '':
        assert metric is not None
        plotdir += '_' + extra_str
    if per_x is not None:
        plotdir += '/' + per_x
    return plotdir

# ----------------------------------------------------------------------------------------
def make_plots(args, action, metric, per_x, choice_grouping, ptilestr, ptilelabel, xvar, min_ptile_to_plot=75., use_relative_affy=False, metric_extra_str='', xdelim='_XTRA_', distr_hists=True, debug=False):
    if metric == 'lbr' and args.dont_observe_common_ancestors:
        print '    skipping lbr when only observing leaves'
        return
    affy_key_str = 'relative-' if (use_relative_affy and ptilestr=='affinity') else ''  # NOTE somewhat duplicates lbplotting.rel_affy_str()
    treat_clusters_together = args.n_sim_events_per_proc is None or (per_x == 'per-seq' and choice_grouping == 'among-families')  # if either there's only one family per proc, or we're choosing cells among all the clusters in a proc together, then things here generally work as if there were only one family per proc (note that I think I don't need the 'per-seq' since it shouldn't be relevant for 'per-cluster', but it makes it clearer what's going on)
    vlabels = {
        'obs_frac' : 'fraction sampled',
        'n-sim-seqs-per-gen' : 'N/gen',
        'obs-times' : 't obs',
        'carry-cap' : 'carry cap',
    }
    treeutils.legtexts.update(lbplotting.metric_for_target_distance_labels)
    def legstr(label, title=False):
        if label is None: return None
        jstr = '\n' if title else '; '
        tmplist = [treeutils.legtexts.get(l, l.replace('-', ' ')) for l in label.split('; ')]
        if title and args.pvks_to_plot is not None:  # if we're only plotting specific values, put them in the legend str (typically we're just plotting one value)
            assert isinstance(args.pvks_to_plot, list)  # don't really need this
            for il in range(len(tmplist)):
                subpvks = [pvk.split('; ')[il] for pvk in args.pvks_to_plot]
                tmplist[il] += ': %s' % ' '.join(treeutils.legtexts.get(spvk, spvk) for spvk in subpvks)
        lstr = jstr.join(tmplist)
        return lstr

    pvlabel = ['?']  # arg, this is ugly (but it does work...)
    # ----------------------------------------------------------------------------------------
    def get_obs_frac(vlists, varnames):
        obs_times = utils.vlval(args, vlists, varnames, 'obs-times')
        n_per_gen_vals = utils.vlval(args, vlists, varnames, 'n-sim-seqs-per-gen')
        if len(obs_times) == len(n_per_gen_vals):  # note that this duplicates logic in bcr-phylo simulator.py
            n_sampled = sum(n_per_gen_vals)
        elif len(n_per_gen_vals) == 1:
            n_sampled = len(obs_times) * n_per_gen_vals[0]
        else:
            assert False
        n_total = utils.vlval(args, vlists, varnames, 'carry-cap')  # note that this is of course the number alive at a given time, and very different from the total number that ever lived
        obs_frac = n_sampled / float(n_total)
        dbgstr = '    %-12s %-12s   %-5d     %8s / %-4d = %.3f' % (' '.join(str(o) for o in obs_times), ' '.join(str(n) for n in n_per_gen_vals), n_total,
                                                                   ('(%s)' % ' + '.join(str(n) for n in n_per_gen_vals)) if len(obs_times) == len(n_per_gen_vals) else ('%d * %d' % (len(obs_times), n_per_gen_vals[0])),
                                                                   n_total, n_sampled / float(n_total))
        return obs_frac, dbgstr
    # ----------------------------------------------------------------------------------------
    def pvkeystr(vlists, varnames, obs_frac):
        def valstr(vname):
            vval = obs_frac if vname == 'obs_frac' else utils.vlval(args, vlists, varnames, vname)
            if vname == 'obs_frac':
                return '%.4f' % obs_frac
            else:
                def strfcn(x):
                    return str(x)  # TODO
                if isinstance(vval, list):
                    return ', '.join(strfcn(v) for v in vval)
                else:
                    return strfcn(vval)
        pvnames = sorted(set(varnames) - set(['seed', xvar]))
        if args.legend_var is not None:  # pvnames == ['n-sim-seqs-per-gen']:  # if this is the only thing that's different between different runs (except for the x variable and seed/replicate) then we want to use obs_frac
            pvnames = [args.legend_var]  # ['obs_frac']
        pvkey = '; '.join(valstr(vn) for vn in pvnames)  # key identifying each line of a different color
        pvlabel[0] = '; '.join(vlabels.get(vn, vn) for vn in pvnames)
        return pvkey
    # ----------------------------------------------------------------------------------------
    def get_ytmpfo(yamlfo, iclust=None):
        if 'percentiles' in yamlfo:  # new-style files
            ytmpfo = yamlfo['distr-hists' if distr_hists else 'percentiles']
            if per_x == 'per-seq':
                ytmpfo = ytmpfo.get('per-seq', ytmpfo)['all-clusters' if iclust is None else 'iclust-%d' % iclust]  # distr-hists don't have 'per-seq'/'per-cluster' level
            else:
                ytmpfo = ytmpfo.get('per-cluster', ytmpfo)[choice_grouping]
        else:  # old-style files
            ytmpfo = yamlfo
            if iclust is not None:
                if 'iclust-%d' % iclust not in ytmpfo:
                    print '    %s requested per-cluster ptile vals, but they\'re not in the yaml file (probably just an old file)' % utils.color('yellow', 'warning')  # I think it's just going to crash on the next line anyway
                ytmpfo = ytmpfo['iclust-%d' % iclust]
        return ytmpfo
    # ----------------------------------------------------------------------------------------
    def yval_key(ytmpfo):
        if ptilestr == 'affinity' and 'mean_affy_ptiles' in ytmpfo:  # old-style files used shortened version
            return 'mean_affy_ptiles'
        else:
            return 'mean_%s_ptiles' % ptilestr
    # ----------------------------------------------------------------------------------------
    def get_diff_vals(ytmpfo, iclust=None):
        # ----------------------------------------------------------------------------------------
        def gethist(tkey):
            yfo = ytmpfo[k]
            htmp = Hist(n_bins=yfo['n_bins'], xmin=yfo['xmin'], xmax=yfo['xmax'])
            for ibin in htmp.ibiniter(True):
                htmp.bin_contents[ibin] = yfo['bin_contents'][ibin]
            return htmp
        # ----------------------------------------------------------------------------------------
        ytmpfo = get_ytmpfo(ytmpfo, iclust=iclust)
        if distr_hists:  # specify args.distr_hist_limit in one of three forms: (N, 3) (take 3 from each family), (frac, 0.01) (take 1% of family/total), or (val, 7) (take those with lb value greater than 7)
            hzero, hother = [gethist(k) for k in ['zero', 'not 0']]
            for tattr in ['n_bins', 'xmin', 'xmax']:
                assert getattr(hzero, tattr) == getattr(hother, tattr)
            if args.distr_hist_limit[0] == 'val':
                ibin = hzero.find_bin(args.distr_hist_limit[1])
            elif args.distr_hist_limit[0] in ['frac', 'N']:
                hsum = copy.deepcopy(hzero)
                hsum.add(hother)
                tsum, total = 0., hsum.integral(True)
                tfrac = args.distr_hist_limit[1]
                if args.distr_hist_limit[0] == 'N':
                    tfrac = args.distr_hist_limit[1] / total
                    if iclust is None:
                        tfrac *= args.n_sim_events_per_proc
                for ibin in hsum.ibiniter(True, reverse=True):
                    tsum += hsum.bin_contents[ibin]
                    if tsum >= tfrac * total:
                        break
            else:
                assert False
            n_zero, n_other = [h.integral(False, ibounds=(ibin, h.n_bins+2)) for h in [hzero, hother]]
            return n_zero, n_other, hzero.low_edges[ibin]
        else:
            return [abs(pafp - afp) for lbp, afp, pafp in zip(ytmpfo['lb_ptiles'], ytmpfo[yval_key(ytmpfo)], ytmpfo['perfect_vals']) if lbp > min_ptile_to_plot]
    # ----------------------------------------------------------------------------------------
    def get_varname_str():
        return ''.join('%10s' % vlabels.get(v, v) for v in varnames)
    def get_varval_str(vstrs):
        return ''.join(' %9s' % v for v in vstrs)
    # ----------------------------------------------------------------------------------------
    def read_plot_info():
        # ----------------------------------------------------------------------------------------
        def add_plot_vals(ytmpfo, vlists, varnames, obs_frac, iclust=None):
            def getikey():
                if args.n_replicates == 1 and treat_clusters_together:
                    ikey = None
                    def initfcn(): return []  # i swear it initially made more sense for this to be such a special case
                elif args.n_replicates == 1:  # but more than one event per proc
                    ikey = iclust
                    def initfcn(): return {i : [] for i in range(args.n_sim_events_per_proc)}
                elif treat_clusters_together:  # but more than one replicate/seed
                    ikey = vlists[varnames.index('seed')]
                    def initfcn(): return {i : [] for i in utils.sargval(args, 'seed')}
                else:  # both of 'em non-trivial
                    ikey = '%d-%d' % (vlists[varnames.index('seed')], iclust)
                    def initfcn(): return {('%d-%d' % (i, j)) : [] for i in utils.sargval(args, 'seed') for j in range(args.n_sim_events_per_proc)}
                return ikey, initfcn

            diff_vals = get_diff_vals(ytmpfo, iclust=iclust)
            if len(diff_vals) == 0:
                missing_vstrs['empty'].append((iclust, vstrs))  # empty may be from empty list in yaml file, or may be from none of them being above <min_ptile_to_plot>
                return
            if distr_hists:
                n_zero, n_other, lo_edge = diff_vals
                if n_zero + n_other == 0:
                    # print '  %s zero total in distr hists' % utils.color('yellow', 'warning')
                    return
                diff_to_perfect =  n_zero / float(n_zero + n_other)
                if debug:
                    nd = str(0 if lo_edge >= 10. else 1)
                    print '%s%d/%d=%.2f (%s)' % ('    ' if iclust in [0, None] else ' ', n_zero, n_zero + n_other, diff_to_perfect, ('%3.'+nd+'f')%lo_edge),
            else:
                diff_to_perfect = numpy.mean(diff_vals)
                if debug:
                    print ' %.2f' % diff_to_perfect,
            tau = utils.vlval(args, vlists, varnames, xvar)  # not necessarily tau anymore
            ikey, initfcn = getikey()
            pvkey = pvkeystr(vlists, varnames, obs_frac)  # key identifying each line in the plot, each with a different color, (it's kind of ugly to get the label here but not use it til we plot, but oh well)
            if pvkey not in plotvals:
                plotvals[pvkey] = initfcn()
            plotlist = plotvals[pvkey][ikey] if ikey is not None else plotvals[pvkey]  # it would be nice if the no-replicate-families-together case wasn't treated so differently
            plotlist.append((tau, diff_to_perfect))  # NOTE this appends to plotvals, the previous line is just to make sure we append to the right place

        # ----------------------------------------------------------------------------------------
        if debug:
            print '%s   | obs times    N/gen        carry cap       fraction sampled           values' % get_varname_str()
        missing_vstrs = {'missing' : [], 'empty' : []}
        for vlists, vstrs in zip(val_lists, valstrs):  # why is this called vstrs rather than vstr?
            obs_frac, dbgstr = get_obs_frac(vlists, varnames)
            if debug:
                print '%s   | %s' % (get_varval_str(vstrs), dbgstr),
            yfname = get_tm_fname(varnames, vstrs, metric, ptilestr, cg=choice_grouping, tv=lbplotting.ungetptvar(ptilestr), use_relative_affy=use_relative_affy, extra_str=metric_extra_str)
            try:
                with open(yfname) as yfile:
                    yamlfo = json.load(yfile)  # too slow with yaml
            except IOError:  # os.path.exists() is too slow with this many files
                missing_vstrs['missing'].append((None, vstrs))
                continue
            # the perfect line is higher for lbi, but lower for lbr, hence the abs(). Occasional values can go past/better than perfect, so maybe it would make sense to reverse sign for lbi/lbr rather than taking abs(), but I think this is better
            if treat_clusters_together:
                add_plot_vals(yamlfo, vlists, varnames, obs_frac)
            else:
                iclusts_in_file = []
                if 'percentiles' in yamlfo:
                    iclusts_in_file = sorted([int(k.split('-')[1]) for k in yamlfo['percentiles']['per-seq'] if 'iclust-' in k])  # if there's info for each cluster, it's in sub-dicts under 'iclust-N' (older files won't have it)
                else:
                    iclusts_in_file = sorted([int(k.split('-')[1]) for k in yamlfo if 'iclust-' in k])  # if there's info for each cluster, it's in sub-dicts under 'iclust-N' (older files won't have it)
                missing_iclusts = [i for i in range(args.n_sim_events_per_proc) if i not in iclusts_in_file]
                if len(missing_iclusts) > 0:
                    print '  %s missing %d/%d iclusts (i = %s) from file %s' % (utils.color('red', 'error'), len(missing_iclusts), args.n_sim_events_per_proc, ' '.join(str(i) for i in missing_iclusts), yfname)
                # assert iclusts_in_file == list(range(args.n_sim_events_per_proc))  # I'm not sure why I added this (presumably because I thought I might not see missing ones any more), but I'm seeing missing ones now (because clusters were smaller than min_selection_metric_cluster_size)
                for iclust in iclusts_in_file:
                    add_plot_vals(yamlfo, vlists, varnames, obs_frac, iclust=iclust)
            if debug:
                print ''

        # print info about missing and empty results
        n_printed, n_max_print = 0, 5
        for mkey, vstrs_list in missing_vstrs.items():  # ok now it's iclust and vstrs list, but what tf am I going to name that
            if len(vstrs_list) == 0:
                continue
            print '        %s: %d families' % (mkey, len(vstrs_list))
            print '     %s   iclust' % get_varname_str()
            for iclust, vstrs in vstrs_list:
                print '      %s    %4s    %s' % (get_varval_str(vstrs), iclust, get_tm_fname(varnames, vstrs, metric, ptilestr, cg=choice_grouping, tv=lbplotting.ungetptvar(ptilestr), use_relative_affy=use_relative_affy, extra_str=metric_extra_str))
                n_printed += 1
                if n_printed >= n_max_print:
                    print '             [...]'
                    print '      skipping %d more lines' % (len(vstrs_list) - n_max_print)
                    break

        # average over the replicates/clusters
        if (args.n_replicates > 1 or not treat_clusters_together) and len(plotvals) > 0:
            if debug:
                print '  averaging over %d replicates' % args.n_replicates,
                if args.n_sim_events_per_proc is not None:
                    if treat_clusters_together:
                        print '(treating %d clusters per proc together)' % args.n_sim_events_per_proc,
                    else:
                        print 'times %d clusters per proc:' % args.n_sim_events_per_proc,
                print ''
                tmplen = str(max(len(pvkey) for pvkey in plotvals))
                print ('    %'+tmplen+'s   N used  N expected') % 'pvkey'
                dbgvals = []
            for pvkey, ofvals in plotvals.items():
                mean_vals, err_vals = [], []
                ofvals = {i : vals for i, vals in ofvals.items() if len(vals) > 0}  # remove zero-length ones (which should [edit: maybe?] correspond to 'missing'). Note that this only removes one where *all* the vals are missing, whereas if they're partially missing they values they do have will get added as usual below
                n_used = []  # just for dbg
                tmpvaldict = collections.OrderedDict()  # rearrange them into a dict keyed by the appropriate tau/xval
                for ikey in ofvals:  # <ikey> is an amalgamation of iseeds and icluster, e.g. '20-0'
                    for pairvals in ofvals[ikey]:
                        tau, tval = pairvals  # reminder: tau is not in general (any more) tau, but is the variable values fulfilling the original purpose of tau (i think x values?) in the plot
                        tkey = tuple(tau) if isinstance(tau, list) else tau  # if it's actually tau, it will be a single value, but if xvar is set to, say, n-sim-seqs-per-gen then it will be a list
                        if tkey not in tmpvaldict:  # these will usually get added in order, except when there's missing ones in some ikeys
                            tmpvaldict[tkey] = []
                        tmpvaldict[tkey].append(tval)
                tvd_keys = sorted(tmpvaldict) if xvar != 'parameter-variances' else tmpvaldict.keys()  # for parameter-variances we want to to keep the original ordering from the command line
                for tau in tvd_keys:  # note that the <ltmp> for each <tau> are in general different if some replicates/clusters are missing or empty
                    ltmp = tmpvaldict[tau]  # len of <ltmp> is N seeds (i.e. procs) times N clusters per seed
                    mean_vals.append((tau, numpy.mean(ltmp)))
                    err_vals.append((tau, numpy.std(ltmp, ddof=1) / math.sqrt(len(ltmp))))  # standard error on mean (for standard deviation, comment out denominator)
                    n_used.append(len(ltmp))
                    if debug:
                        dbgvals.append((tau, mean_vals[-1][1], err_vals[-1][1]))
                plotvals[pvkey] = mean_vals
                errvals[pvkey] = err_vals
                if debug:
                    n_expected = args.n_replicates
                    if not treat_clusters_together:
                        n_expected *= args.n_sim_events_per_proc
                    print ('    %'+tmplen+'s    %s   %4d%s') % (pvkey, ('%4d' % n_used[0]) if len(set(n_used)) == 1 else utils.color('red', ' '.join(str(n) for n in set(n_used))), n_expected, '' if n_used[0] == n_expected else utils.color('red', ' <--'))
            if debug:
                print '    final values:'
                for tau, meanval, errval in dbgvals:
                    print '     %6s  %5.2f +/- %.1f' % (tau, meanval, errval)
    # ----------------------------------------------------------------------------------------
    def plotcall(pvkey, xticks, diffs_to_perfect, yerrs, mtmp, ipv=None, imtmp=None, label=None, dummy_leg=False, alpha=0.5, estr=''):
        markersize = 15  # 1 if len(xticks) > 1 else 15
        linestyle = linestyles.get(mtmp, '-')
        if args.plot_metrics.count(mtmp) > 1 and estr != '':
            linestyle = 'dotted'
        linewidth = linewidths.get(mtmp, 3)
        color = None
        if ipv is not None:
            color = plotting.frozen_pltcolors[ipv % len(plotting.frozen_pltcolors)]
        elif imtmp is not None:  # used to us <imtmp> to directly get color, but now we want to get the same colors no matter the matplotlib version and order on the command line, so now it just indicates that we should add the metric str
            # color = plotting.frozen_pltcolors[imtmp % len(plotting.pltcolors)]
            color = metric_color(mtmp)
        if yerrs is not None:
            ax.errorbar(xticks, diffs_to_perfect, yerr=yerrs, label=legstr(label), color=color, alpha=alpha, linewidth=linewidth, markersize=markersize, marker='.', linestyle=linestyle)  #, title='position ' + str(position))
        else:
            ax.plot(xticks, diffs_to_perfect, label=legstr(label), color=color, alpha=alpha, linewidth=linewidth)
        if dummy_leg:
            dlabel = mtmp
            if not args.dont_plot_extra_strs and estr != '':
                dlabel += ' %s' % estr
            ax.plot([], [], label=legstr(dlabel), alpha=alpha, linewidth=linewidth, linestyle=linestyle, color='grey' if ipv is not None else color, marker='.', markersize=0)
        # elif estr != '':
        #     fig.text(0.5, 0.7, estr, color='red', fontweight='bold')
    # ----------------------------------------------------------------------------------------
    def getplotname(mtmp):
        if per_x == 'per-seq':
            return '%s%s-%s-ptiles-vs-%s-%s' % (affy_key_str, ptilestr, mtmp if mtmp is not None else 'combined', xvar, choice_grouping)
        else:
            return '%s-ptiles-vs-%s' % (choice_grouping.replace('-vs', ''), xvar)
    # ----------------------------------------------------------------------------------------
    def yfname(mtmp, estr):
        return '%s/%s.yaml' % (get_comparison_plotdir(mtmp, per_x, extra_str=estr), getplotname(mtmp))
    # ----------------------------------------------------------------------------------------
    def getxticks(xvals):
        xlabel = treeutils.legtexts.get(xvar, xvar.replace('-', ' '))
        if xvar == 'parameter-variances':  # special case cause we don't parse this into lists and whatnot here
            xticks, xticklabels = [], []
            global_pv_vars = None
            for ipv, pv_cft_str in enumerate(xvals):  # <pv_cft_str> corresponds to one bcr-phylo run, but can contain more than one parameter variance specification
                xticks.append(ipv)
                pv_vars, xtl_strs = [], []
                for pvar_str in pv_cft_str.split('_c_'):
                    assert '..' in pvar_str  # don't handle the uniform-distribution-with-variance method a.t.m.
                    pvar, pvals = pvar_str.split(',')
                    def fmt(v, single=False):
                        if pvar == 'selection-strength':
                            if v == 1.: fstr = '%.0f'
                            else: fstr = '%.2f' if single else '%.1f'
                        else:
                            fstr = '%d'
                        return fstr % v
                    pv_vars.append(pvar)
                    pvlist = [float(pv) for pv in pvals.split('..')]
                    xtlstr = '%s-%s'%(fmt(min(pvlist)), fmt(max(pvlist))) if min(pvlist) != max(pvlist) else fmt(pvlist[0], single=True)
                    xtl_strs.append(xtlstr)
                xticklabels.append('\n'.join(xtl_strs))
                if global_pv_vars is None:
                    global_pv_vars = pv_vars
                if pv_vars != global_pv_vars:
                    raise Exception('each bcr-phylo run has to have the same variables with parameter variances, but got %s and %s' % (global_pv_vars, pv_vars))
            xlabel = ', '.join(treeutils.legtexts.get(p, p.replace('-', ' ')) for p in global_pv_vars)
        elif isinstance(xvals[0], tuple) or isinstance(xvals[0], list):  # if it's a tuple/list (not sure why it's sometimes one vs other times the other), use (more or less arbitrary) integer x axis values
            def tickstr(t):
                if len(t) < 4:
                    return ', '.join(str(v) for v in t)
                else:
                    return '%s -\n %s\n(%d)' % (t[0], t[-1], len(t)) #, t[1] - t[0])
            xticks = list(range(len(xvals)))
            xticklabels = [tickstr(t) for t in xvals]
        else:
            xticks = xvals
            xticklabels = [str(t) for t in xvals]
        return xticks, xticklabels, xlabel

    # ----------------------------------------------------------------------------------------
    _, varnames, val_lists, valstrs = utils.get_var_info(args, args.scan_vars['get-tree-metrics'])
    plotvals, errvals = collections.OrderedDict(), collections.OrderedDict()
    fig, ax = plotting.mpl_init()
    xticks, xlabel = None, None
    if action == 'plot':
        read_plot_info()
        outfo = []
        if len(plotvals) == 0:
            print '  %s no plotvals for %s %s %s' % (utils.color('yellow', 'warning'), metric, per_x, choice_grouping)
            return
        for ipv, pvkey in enumerate(plotvals):
            xvals, diffs_to_perfect = zip(*plotvals[pvkey])
            xticks, xticklabels, xlabel = getxticks(xvals)
            # assert xvals == tuple(sorted(xvals))  # this definitely can happen, but maybe not atm? and maybe not a big deal if it does. So maybe should remove this
            yerrs = zip(*errvals[pvkey])[1] if pvkey in errvals else None  # each is pairs tau, err
            plotcall(pvkey, xticks, diffs_to_perfect, yerrs, metric, ipv=ipv, label=pvkey, estr=metric_extra_str)
            outfo.append((pvkey, {'xvals' : xvals, 'yvals' : diffs_to_perfect, 'yerrs' : yerrs}))
        with open(yfname(metric, metric_extra_str), 'w') as yfile:  # write json file to be read by 'combine-plots'
            json.dump(outfo, yfile)
        title = lbplotting.mtitlestr(per_x, metric, short=True, max_len=7) + ': '
        plotdir = get_comparison_plotdir(metric, per_x, extra_str=metric_extra_str)
        ylabelstr = metric.upper()
    elif action == 'combine-plots':
        pvks_from_args = set([pvkeystr(vlists, varnames, get_obs_frac(vlists, varnames)[0]) for vlists in val_lists])  # have to call this fcn at least once just to set pvlabel (see above) [but now we're also using the results below UPDATE nvmd didn't end up doing it that way, but I'm leaving the return value there in case I want it later]
        plotfos = collections.OrderedDict()
        for mtmp, estr in zip(args.plot_metrics, args.plot_metric_extra_strs):
            if ptilestr not in [v for v, l in lbplotting.single_lbma_cfg_vars(mtmp, final_plots=True)]:  # i.e. if the <ptilestr> (variable name) isn't in any of the (variable name, label) pairs (e.g. n-ancestor for lbi; we need this here because of the set() in the calling block)
                continue
            if not os.path.exists(yfname(mtmp, estr)):
                print '    %s missing %s' % (utils.color('yellow', 'warning'), yfname(mtmp, estr))
                continue
            with open(yfname(mtmp, estr)) as yfile:
                mkey = mtmp
                if estr != '':
                    mkey = '%s%s%s' % (mtmp, xdelim, estr)  # this is ugly, but we need to be able to split it apart in the loop just below here
                plotfos[mkey] = collections.OrderedDict(json.load(yfile))
                if len(plotfos[mkey]) == 0:
                    raise Exception('read zero length info from %s' % yfname(mtmp, estr))  # if this happens when we're writing the file (above), we can skip it, but  I think we have to crash here (just rerun without this metric/extra_str). It probably means you were missing the dtr files for this per_x/cgroup
        if len(plotfos) == 0:
            print '  nothing to plot'
            return
        pvks_from_file = set([tuple(pfo.keys()) for pfo in plotfos.values()])  # list of lists of pv keys (to make sure the ones from each metric's file are the same)
        if len(pvks_from_file) > 1:  # eh, they can be different now if I ran different metrics with different argument lists
            print '  %s different lists of pv keys for different metrics: %s' % (utils.color('yellow', 'warning'), pvks_from_file)
            pvk_list = sorted(pvks_from_file, key=len)[0]  # use the shortest one
        else:
            pvk_list = list(pvks_from_file)[0]
        if args.pvks_to_plot is not None:
            # pvk_list = [p for p in list(pvks_from_file)[0] if p in pvks_from_args]  # don't do it this way since if you only ask it to plot one value it'll get the wrong file path (since it'll no longer make a subdir level for that variable)
            ptmp = [p for p in pvk_list if p in args.pvks_to_plot]
            if len(ptmp) == 0:
                raise Exception('requirement in --pvks-to-plot \'%s\' didn\'t give us any from the list %s' % (args.pvks_to_plot, pvk_list))
            pvk_list = ptmp
        for ipv, pvkey in enumerate(pvk_list):
            for imtmp, (mkey, pfo) in enumerate(plotfos.items()):
                mtmp, estr = (mkey, '') if xdelim not in mkey else mkey.split(xdelim)
                xticks, xticklabels, xlabel = getxticks(pfo[pvkey]['xvals'])
                plotcall(pvkey, xticks, pfo[pvkey]['yvals'], pfo[pvkey]['yerrs'], mtmp, label=pvkey if (imtmp == 0 and len(pvk_list) > 1) else None, ipv=ipv if len(pvk_list) > 1 else None, imtmp=imtmp, dummy_leg=ipv==0, estr=estr)
        # if ''.join(args.plot_metric_extra_strs) == '':  # no extra strs
        #     title = '+'.join(plotfos) + ': '
        # else:
        #     title = '+'.join(set(args.plot_metrics)) + ': '
        title = ''
        plotdir = get_comparison_plotdir('combined', per_x)
        ylabelstr = 'metric'
    else:
        assert False

    ymin, ymax = ax.get_ylim()
    # if ptilestr == 'affinity':
    #     ymin, ymax = 0, max(ymax, 25)
    # elif ptilestr == 'n-ancestors':
    #     ymin, ymax = 0, max(ymax, 1.5)

    log, adjust = '', {}
    if xvar == 'lb-tau' and len(xticks) > 1:
        ax.plot([1./args.seq_len, 1./args.seq_len], (ymin, ymax), linewidth=3, alpha=0.7, color='darkred', linestyle='--') #, label='1/seq len')
    if xvar == 'carry-cap':
        log = 'x'

    if ax.get_ylim()[1] < 1:
        adjust['left'] = 0.21
    if ax.get_ylim()[1] < 0.01:
        adjust['left'] = 0.26
    adjust['bottom'] = 0.25
    adjust['top'] = 0.9
    if xticklabels is not None and '\n' in xticklabels[0]:
        adjust['bottom'] = 0.3
        import matplotlib.pyplot as plt
        plt.xlabel('xlabel', fontsize=14)

    n_ticks = 4
    dy = (ymax - ymin) / float(n_ticks - 1)
    yticks, yticklabels = None, None
    # if ptilestr != 'affinity':
    #     yticks = [int(y) if ptilestr == 'affinity' else utils.round_to_n_digits(y, 3) for y in numpy.arange(ymin, ymax + 0.5*dy, dy)]
    #     yticklabels = ['%s'%y for y in yticks]
    if per_x == 'per-seq':
        title += 'choosing %s' % (choice_grouping.replace('within-families', 'within each family').replace('among-', 'among all '))
    if use_relative_affy:
        fig.text(0.5, 0.87, 'relative %s' % ptilestr, fontsize=15, color='red', fontweight='bold')
    leg_loc = [0.04, 0.6]
    # if metric != 'lbi' and len(title) < 17:
    #     leg_loc[0] = 0.7
    if distr_hists:
        ylabel = 'frac. correct'
        if args.distr_hist_limit[0] == 'val':
            ylabel += ' (%s > %.1f)' % (lbplotting.mtitlestr(per_x, metric, short=True, max_len=7), args.distr_hist_limit[1])
        elif args.distr_hist_limit[0] == 'frac':
            ylabel += ' (top %.0f%%)' % (100*args.distr_hist_limit[1])
        elif args.distr_hist_limit[0] == 'N':
            ylabel += ' (top %d per family)' % args.distr_hist_limit[1]
        else:
            assert False
    else:
        ylabel = '%s to perfect' % ('percentile' if ptilelabel == 'affinity' else ptilelabel)
    plotting.mpl_finish(ax, plotdir, getplotname(metric),
                        xlabel=xlabel,
                        # ylabel='%s to perfect\nfor %s ptiles in [%.0f, 100]' % ('percentile' if ptilelabel == 'affinity' else ptilelabel, ylabelstr, min_ptile_to_plot),
                        ylabel=ylabel,
                        title=title, leg_title=legstr(pvlabel[0], title=True), leg_prop={'size' : 12}, leg_loc=leg_loc,
                        xticks=xticks, xticklabels=xticklabels, xticklabelsize=12 if xticklabels is not None and '\n' in xticklabels[0] else 16,
                        yticks=yticks, yticklabels=yticklabels,
                        ybounds=(ymin, ymax), log=log, adjust=adjust,
    )

# ----------------------------------------------------------------------------------------
def run_bcr_phylo(args):  # also caches parameters
    base_args, varnames, _, valstrs = utils.get_var_info(args, args.scan_vars['simu'])
    cmdfos = []
    print '  bcr-phylo: running %d combinations of: %s' % (len(valstrs), ' '.join(varnames))
    if args.debug:
        print '   %s' % ' '.join(varnames)
    n_already_there = 0
    for icombo, vstrs in enumerate(valstrs):
        if args.debug:
            print '   %s' % ' '.join(vstrs)
        outdir = get_bcr_phylo_outdir(varnames, vstrs)
        if utils.output_exists(args, get_partition_fname(varnames, vstrs, 'bcr-phylo'), offset=8, debug=args.debug):
            n_already_there += 1
            continue
        cmd = './bin/bcr-phylo-run.py --actions %s --dont-get-tree-metrics --base-outdir %s %s' % (args.bcr_phylo_actions, outdir, ' '.join(base_args))
        for vname, vstr in zip(varnames, vstrs):
            vstr_for_cmd = vstr
            if vname == 'parameter-variances':
                vstr_for_cmd = vstr_for_cmd.replace('_c_', ':')  # necessary so we can have multiple different parameters with variances for each bcr-phylo-run.py cmd
            cmd += ' --%s %s' % (vname, vstr_for_cmd)
            if 'context' in vname:
                cmd += ' --restrict-available-genes'
        if args.no_scan_parameter_variances is not None:
            cmd += ' --parameter-variances %s' % args.no_scan_parameter_variances  # we don't parse through this at all here, which means it's the same for all combos of variables (which I think makes sense -- we probably don't even really want to vary most variables if this is set)
        if args.n_sim_events_per_proc is not None:
            cmd += ' --n-sim-events %d' % args.n_sim_events_per_proc
        if args.n_max_queries is not None:
            cmd += ' --n-max-queries %d' % args.n_max_queries
        if args.dont_observe_common_ancestors:
            cmd += ' --dont-observe-common-ancestors'
        if args.overwrite:
            cmd += ' --overwrite'
        if args.only_csv_plots:
            cmd += ' --only-csv-plots'
        if args.n_sub_procs > 1:
            cmd += ' --n-procs %d' % args.n_sub_procs
        if args.sub_slurm:
            cmd += ' --slurm'
        # cmd += ' --debug 2'
        cmdfos += [{
            'cmd_str' : cmd,
            'outfname' : get_partition_fname(varnames, vstrs, 'bcr-phylo'),
            'logdir' : outdir,
            'workdir' : '%s/bcr-phylo-work/%d' % (args.workdir, icombo),
        }]
    if n_already_there > 0:
        print '      %d / %d skipped (outputs exist, e.g. %s)' % (n_already_there, len(valstrs), get_partition_fname(varnames, vstrs, 'bcr-phylo'))
    if len(cmdfos) > 0:
        if args.dry:
            print '    %s' % '\n    '.join(cfo['cmd_str'] for cfo in cmdfos)
        else:
            print '      starting %d jobs' % len(cmdfos)
            utils.run_cmds(cmdfos, debug='write:bcr-phylo.log', batch_system='slurm' if args.slurm else None, n_max_procs=args.n_max_procs, allow_failure=True)

# ----------------------------------------------------------------------------------------
def get_tree_metrics(args):
    _, varnames, _, valstrs = utils.get_var_info(args, args.scan_vars['get-tree-metrics'])  # can't use base_args a.t.m. since it has the simulation/bcr-phylo args in it
    cmdfos = []
    print '  get-tree-metrics (%s): running %d combinations of: %s' % (args.metric_method, len(valstrs), ' '.join(varnames))
    n_already_there = 0
    for icombo, vstrs in enumerate(valstrs):
        if args.debug:
            print '   %s' % ' '.join(vstrs)

        if utils.all_outputs_exist(args, get_all_tm_fnames(varnames, vstrs, metric_method=args.metric_method, extra_str=args.extra_plotstr), outlabel='get-tree-metrics', offset=8, debug=args.debug):
            n_already_there += 1
            continue

        if not args.dry:
            tmpoutdir = get_tree_metric_outdir(varnames, vstrs, metric_method=args.metric_method)
            if not os.path.isdir(tmpoutdir):
                os.makedirs(tmpoutdir)

        # it would probably be better to use dtr-run.py for everything, but then i'd be nervous i wasn't testing the partitiondriver version of the code enough UPDATE can now use it for lbi/lbr
        tmpdir = get_tree_metric_plotdir(varnames, vstrs, metric_method=None if args.metric_method in ['lbi', 'lbr'] else args.metric_method, extra_str=args.extra_plotstr)  # if we're running lbi/lbr as a --metric-method to avoid running partis get-selection-metrics
        if args.metric_method is None:  # lb metrics, i.e. actually running partis and getting tree metrics
            cmd = './bin/partis get-selection-metrics --is-simu --infname %s --plotdir %s --outfname %s --selection-metric-fname %s' % (get_simfname(varnames, vstrs), tmpdir,
                                                                                                                                        get_partition_fname(varnames, vstrs, 'bcr-phylo'), utils.insert_before_suffix('-selection-metrics', get_partition_fname(varnames, vstrs, 'get-tree-metrics')))  # we don't actually use the --selection-metric-fname for anything, but if we don't set it then all the different get-tree-metric jobs write their output files to the same selection metric file in the bcr-phylo dir
            cmd += ' --seed %s' % args.random_seed  # NOTE second/commented version this is actually wrong: vstrs[varnames.index('seed')]  # there isn't actually a reason for different seeds here (we want the different seeds when running bcr-phylo), but oh well, maybe it's a little clearer this way
            if args.no_tree_plots:
                cmd += ' --ete-path None'
            # if args.n_sub_procs > 1:  # TODO get-tree-metrics doesn't paralellize anything atm
            #     cmd += ' --n-procs %d' % args.n_sub_procs
        else:  # non-lb metrics, i.e. trying to predict with shm, etc.
            cmd = './bin/dtr-run.py --metric-method %s --infname %s --base-plotdir %s' % (args.metric_method,
                                                                                          get_simfname(varnames, vstrs),
                                                                                          tmpdir)
            if args.metric_method == 'dtr':
                if args.train_dtr and args.overwrite:  # make sure no training files exist, since we don\'t want treeutils.train_dtr_model() to overwrite existing ones (since training can be really slow)
                    assert set([os.path.exists(f) for f in get_all_tm_fnames(varnames, vstrs, metric_method=args.metric_method, extra_str=args.extra_plotstr)]) == set([False])
                cmd += ' --action %s' % ('train' if args.train_dtr else 'test')
                cmd += ' --dtr-path %s' % (args.dtr_path if args.dtr_path is not None else get_dtr_model_dir(varnames, vstrs, extra_str=args.extra_plotstr))  # if --dtr-path is set, we're reading the model from there; otherwise we write a new model to the normal/auto location for these parameters (i.e. the point of --dtr-path is to point at the location from a different set of parameters)
                if args.dtr_cfg is not None:
                    cmd += ' --dtr-cfg %s' % args.dtr_cfg
            if not args.only_csv_plots and not args.no_tree_plots:
                cmd += ' --make-tree-plots'
        cmd += ' --lb-tau %s' % utils.vlval(args, vstrs, varnames, 'lb-tau')
        if len(args.lb_tau_list) > 1:
            cmd += ' --lbr-tau-factor 1 --dont-normalize-lbi'
        if args.only_csv_plots:
            cmd += ' --only-csv-plots'
        if args.n_max_queries is not None:
            cmd += ' --n-max-queries %d' % args.n_max_queries
        cmd += ' --min-selection-metric-cluster-size 5'  # if n per gen is small, sometimes the clusters are a bit smaller than 10, but we don't really want to skip any clusters here (especially because it confuses the plotting above)
        if args.include_relative_affy_plots:
            cmd += ' --include-relative-affy-plots'

        cmdfos += [{
            'cmd_str' : cmd,
            'outfname' : get_all_tm_fnames(varnames, vstrs, metric_method=args.metric_method, extra_str=args.extra_plotstr)[0],
            'workdir' : tmpdir,
        }]

    if n_already_there > 0:
        print '      %d / %d skipped (outputs exist, e.g. %s)' % (n_already_there, len(valstrs), get_all_tm_fnames(varnames, vstrs, metric_method=args.metric_method, extra_str=args.extra_plotstr)[0])
    if len(cmdfos) > 0:
        print '      %s %d jobs' % ('--dry: would start' if args.dry else 'starting', len(cmdfos))
        if args.dry:
            print '  first command: %s' % cmdfos[0]['cmd_str']
        else:
            logstr = 'get-tree-metrics'
            if args.metric_method == 'dtr':
                logstr += '-train' if args.train_dtr else '-test'
            utils.run_cmds(cmdfos, debug='write:%s.log'%logstr, batch_system='slurm' if args.slurm else None, n_max_procs=args.n_max_procs, allow_failure=True)

# ----------------------------------------------------------------------------------------
all_actions = ['get-lb-bounds', 'bcr-phylo', 'get-tree-metrics', 'plot', 'combine-plots']
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--actions', default=':'.join(a for a in all_actions if a not in ['get-lb-bounds', 'combine-plots']))
parser.add_argument('--bcr-phylo-actions', default='simu:cache-parameters:partition')
parser.add_argument('--test', action='store_true')
parser.add_argument('--carry-cap-list', default='1000')
parser.add_argument('--n-sim-seqs-per-gen-list', default='30:50:75:100:150:200', help='colon-separated list of comma-separated lists of the number of sequences for bcr-phylo to sample at the times specified by --obs-times-list')
parser.add_argument('--n-sim-events-per-proc', type=int, help='number of rearrangement events to simulate in each process (default is set in bin/bcr-phylo-run.py)')
parser.add_argument('--obs-times-list', default='125,150', help='colon-separated list of comma-separated lists of bcr-phylo observation times')
parser.add_argument('--lb-tau-list', default='0.0005:0.001:0.002:0.003:0.004:0.008:0.012')
parser.add_argument('--metric-for-target-distance-list', default='aa')  # it would be nice to not set defaults here, since it clutters up the bcr-phylo simulator.py calls, but this insulates us against the defaults in bcr-phylo simulator.py changing at some point
parser.add_argument('--leaf-sampling-scheme-list', default='uniform-random')
parser.add_argument('--target-count-list', default='1')
parser.add_argument('--n-target-clusters-list')  # NOTE do *not* set a default here, since in bcr-phylo simulator.py the default is None
parser.add_argument('--min-target-distance-list')
parser.add_argument('--context-depend-list')
parser.add_argument('--paratope-positions-list')
parser.add_argument('--metric-method', choices=['shm', 'fay-wu-h', 'cons-dist-nuc', 'cons-dist-aa', 'delta-lbi', 'lbi', 'aa-lbi', 'lbr', 'aa-lbr', 'dtr', 'cons-lbi'], help='method/metric to compare to/correlate with affinity (for use with get-tree-metrics action). If not set, run partis to get lb metrics. UPDATE can now run this way also for plain/nuc lbi and lbr.')
parser.add_argument('--plot-metrics', default='lbi:lbr')  # don't add dtr until it can really run with default options (i.e. model files are really settled)
parser.add_argument('--plot-metric-extra-strs', help='extra strs for each metric in --plot-metrics (i.e. corresponding to what --extra-plotstr was set to during get-tree-metrics for that metric)')
parser.add_argument('--dont-plot-extra-strs', action='store_true', help='while we still use the strings in --plot-metric-extra-strs to find the right dir to get the plot info from, we don\'t actually put the str in the plot (i.e. final plot versions where we don\'t want to see which dtr version it is)')
parser.add_argument('--combo-extra-str', help='extra label for combine-plots action i.e. write to combined-%s/ subdir instead of combined/')
parser.add_argument('--distr-hist-limit', default='frac:0.03', help='lower bound type:value to use for new distribution performance hists for delta affinity metrics (aa-lbr/lbr). frac:<f> takes the top 100*<f>\%, N:<n> takes the top <n> seqs, val:<v> takes all seqs with metric value above <v>.')
parser.add_argument('--pvks-to-plot', help='only plot these line/legend values when combining plots')
parser.add_argument('--train-dtr', action='store_true')
parser.add_argument('--dtr-path', help='Path from which to read decision tree regression training data. If not set (and --metric-method is dtr), we use a default (see --train-dtr).')
parser.add_argument('--dtr-cfg', help='yaml file with dtr training parameters (read by treeutils.calculate_non_lb_tree_metrics()). If not set, default parameters are taken from treeutils.py')
parser.add_argument('--selection-strength-list', default='1.0')
parser.add_argument('--no-scan-parameter-variances', help='Configures parameter variance among families (see bcr-phylo-run.py help for details). Use this version if you only want *one* combination, i.e. if you\'re not scanning across variable combinations: all the different variances go into one bcr-phylo-run.py run (this could be subsumed into the next arg, but for backwards compatibility/cmd line readability it\'s nice to keep it).')
parser.add_argument('--parameter-variances-list', help='Configures parameter variance among families (see bcr-phylo-run.py help for details). Use this version for scanning several combinations. Colons \':\' separate different bcr-phylo-run.py runs, while \'_c_\' separate parameter-variances for multiple variables within each bcr-phylo-run.py run.')
parser.add_argument('--dont-observe-common-ancestors', action='store_true')
parser.add_argument('--zip-vars', help='colon-separated list of variables for which to pair up values sequentially, rather than doing all combinations')
parser.add_argument('--seq-len', default=400, type=int)
parser.add_argument('--n-replicates', default=1, type=int)
parser.add_argument('--iseeds', help='if set, only run these replicate indices (i.e. these corresponds to the increment *above* the random seed)')
parser.add_argument('--n-max-procs', type=int, help='Max number of *child* procs (see --n-sub-procs). Default (None) results in no limit.')
parser.add_argument('--n-sub-procs', type=int, default=1, help='Max number of *grandchild* procs (see --n-max-procs)')
parser.add_argument('--n-max-queries', type=int, help='stop after reading this many queries from whatever is input file for this step (NOTE doesn\'t necessarily work for every action)')
parser.add_argument('--random-seed', default=0, type=int, help='note that if --n-replicates is greater than 1, this is only the random seed of the first replicate')
parser.add_argument('--base-outdir', default='%s/partis/tree-metrics' % os.getenv('fs', default=os.getenv('HOME')))
parser.add_argument('--label', default='test')
parser.add_argument('--extra-plotstr', default='', help='if set, put plots resulting from \'get-tree-metrics\' into a separate subdir using this string, rather than just plots/ (e.g. for plotting with many different dtr versions)')
parser.add_argument('--include-relative-affy-plots', action='store_true')
parser.add_argument('--only-csv-plots', action='store_true', help='only write csv/yaml versions of plots (for future parsing), and not the actual svg files (which is slow)')
parser.add_argument('--no-tree-plots', action='store_true', help='don\'t make any of the tree plots, which are slow (this just sets --ete-path to None)')
parser.add_argument('--overwrite', action='store_true')  # not really propagated to everything I think
parser.add_argument('--debug', action='store_true')
parser.add_argument('--dry', action='store_true')
parser.add_argument('--slurm', action='store_true', help='run child procs with slurm')
parser.add_argument('--sub-slurm', action='store_true', help='run grandchild procs with slurm')
parser.add_argument('--workdir')  # default set below
parser.add_argument('--final-plot-xvar', default='lb-tau', help='variable to put on the x axis of the final comparison plots')
parser.add_argument('--legend-var')
parser.add_argument('--partis-dir', default=os.getcwd(), help='path to main partis install dir')
parser.add_argument('--ete-path', default=('/home/%s/anaconda_ete/bin' % os.getenv('USER')) if os.getenv('USER') is not None else None)
# specific to get-lb-bounds:
parser.add_argument('--n-tau-lengths-list', help='set either this or --n-generations-list')
parser.add_argument('--n-generations-list', default='4:5:6:7:8:9:10:12', help='set either this or --n-tau-lengths-list')  # going to 20 uses a ton of memory, not really worth waiting for
parser.add_argument('--max-lb-n-offspring', default=2, type=int, help='multifurcation number for max lb calculation')
parser.add_argument('--only-metrics', default='lbi:lbr', help='which (of lbi, lbr) metrics to do lb bound calculation')
parser.add_argument('--make-plots', action='store_true', help='note: only for get-lb-bounds')
args = parser.parse_args()

args.scan_vars = {'simu' : ['carry-cap', 'n-sim-seqs-per-gen', 'obs-times', 'seed', 'metric-for-target-distance', 'selection-strength', 'leaf-sampling-scheme', 'target-count', 'n-target-clusters', 'min-target-distance', 'context-depend', 'paratope-positions', 'parameter-variances'],}
args.scan_vars['get-tree-metrics'] = args.scan_vars['simu'] + ['lb-tau']
args.str_list_vars = ['n-sim-seqs-per-gen', 'obs-times', 'context-depend', 'n-sim-seqs-per-gen', 'obs-times', 'context-depend']

sys.path.insert(1, args.partis_dir + '/python')
try:
    import utils
    import treeutils
    import plotting
    import lbplotting
    from hist import Hist
except ImportError as e:
    print e
    raise Exception('couldn\'t import from main partis dir \'%s\' (set with --partis-dir)' % args.partis_dir)

args.actions = utils.get_arg_list(args.actions, choices=all_actions)
args.zip_vars = utils.get_arg_list(args.zip_vars)
args.carry_cap_list = utils.get_arg_list(args.carry_cap_list, intify=True, forbid_duplicates=args.zip_vars is None or 'carry-cap' not in args.zip_vars)  # if we're zipping the var, we have to allow duplicates, but then check for them again after we've done combos in get_var_info()
args.n_sim_seqs_per_gen_list = utils.get_arg_list(args.n_sim_seqs_per_gen_list, list_of_lists=True, intify=True, forbid_duplicates=args.zip_vars is None or 'n-sim-seqs-per-gen' not in args.zip_vars)
args.obs_times_list = utils.get_arg_list(args.obs_times_list, list_of_lists=True, intify=True, forbid_duplicates=args.zip_vars is None or 'obs-times' not in args.zip_vars)
args.lb_tau_list = utils.get_arg_list(args.lb_tau_list, floatify=True, forbid_duplicates=True)
args.metric_for_target_distance_list = utils.get_arg_list(args.metric_for_target_distance_list, forbid_duplicates=True, choices=['aa', 'nuc', 'aa-sim-ascii', 'aa-sim-blosum'])
args.leaf_sampling_scheme_list = utils.get_arg_list(args.leaf_sampling_scheme_list, forbid_duplicates=True, choices=['uniform-random', 'affinity-biased', 'high-affinity'])  # WARNING 'high-affinity' gets called 'perfect' in the legends and 'affinity-biased' gets called 'high affinity'
args.target_count_list = utils.get_arg_list(args.target_count_list, forbid_duplicates=True)
args.n_target_clusters_list = utils.get_arg_list(args.n_target_clusters_list, forbid_duplicates=True)
args.min_target_distance_list = utils.get_arg_list(args.min_target_distance_list, forbid_duplicates=True)
args.context_depend_list = utils.get_arg_list(args.context_depend_list, forbid_duplicates=True)
args.paratope_positions_list = utils.get_arg_list(args.paratope_positions_list, forbid_duplicates=True, choices=['all', 'cdrs'])
args.parameter_variances_list = utils.get_arg_list(args.parameter_variances_list, forbid_duplicates=True)
args.plot_metrics = utils.get_arg_list(args.plot_metrics)
args.plot_metric_extra_strs = utils.get_arg_list(args.plot_metric_extra_strs)
if args.plot_metric_extra_strs is None:
    args.plot_metric_extra_strs = ['' for _ in args.plot_metrics]
if len(args.plot_metrics) != len(args.plot_metric_extra_strs):
    raise Exception('--plot-metrics %d not same length as --plot-metric-extra-strs %d' % (len(args.plot_metrics), len(args.plot_metric_extra_strs)))
args.pvks_to_plot = utils.get_arg_list(args.pvks_to_plot)
args.distr_hist_limit = utils.get_arg_list(args.distr_hist_limit) #, key_val_pairs=True)
assert args.distr_hist_limit[0] in ['N', 'frac', 'val']
args.distr_hist_limit[1] = float(args.distr_hist_limit[1])
args.selection_strength_list = utils.get_arg_list(args.selection_strength_list, floatify=True, forbid_duplicates=True)
args.n_tau_lengths_list = utils.get_arg_list(args.n_tau_lengths_list, floatify=True)
args.n_generations_list = utils.get_arg_list(args.n_generations_list, intify=True)
args.only_metrics = utils.get_arg_list(args.only_metrics)
args.iseeds = utils.get_arg_list(args.iseeds, intify=True)
if [args.n_tau_lengths_list, args.n_generations_list].count(None) != 1:
    raise Exception('have to set exactly one of --n-tau-lengths, --n-generations')

import random
random.seed(args.random_seed)  # somehow this is necessary to get the same results, even though I'm not using the module anywhere directly
numpy.random.seed(args.random_seed)

if args.workdir is None:
    args.workdir = utils.choose_random_subdir('/tmp/%s/hmms' % (os.getenv('USER', default='partis-work')))

# ----------------------------------------------------------------------------------------
for action in args.actions:
    if action == 'get-lb-bounds':
        calc_lb_bounds(args)
    elif action == 'bcr-phylo':
        run_bcr_phylo(args)
    elif action == 'get-tree-metrics':
        get_tree_metrics(args)
    elif action in ['plot', 'combine-plots'] and not args.dry:
        assert args.extra_plotstr == ''  # only use --extra-plotstr for get-tree-metrics, for this use --plot-metric-extra-strs (because we in general have multiple --plot-metrics when we're here)
        assert args.metric_method is None  # when plotting, you should only be using --plot-metrics
        _, varnames, val_lists, valstrs = utils.get_var_info(args, args.scan_vars['get-tree-metrics'])
        print 'plotting %d combinations of %d variable%s (%s) with %d families per combination to %s' % (len(valstrs), len(varnames), utils.plural(len(varnames)), ', '.join(varnames), 1 if args.n_sim_events_per_proc is None else args.n_sim_events_per_proc, get_comparison_plotdir(None, None))
        procs = []
        pchoice = 'per-seq'
        if action == 'plot':
            for metric, estr in zip(args.plot_metrics, args.plot_metric_extra_strs):
                utils.prep_dir(get_comparison_plotdir(metric, None, extra_str=estr), subdirs=[pchoice], wildlings=['*.html', '*.svg', '*.yaml'])
                cfg_list = lbplotting.single_lbma_cfg_vars(metric)
                cfg_list = lbplotting.add_use_relative_affy_stuff(cfg_list, include_relative_affy_plots=args.include_relative_affy_plots)
                for ptvar, ptlabel, use_relative_affy in cfg_list:
                    print '  %s  %-s %-13s%-s' % (utils.color('blue', metric), utils.color('purple', estr, width=20, padside='right') if estr != '' else 20*' ', ptvar, utils.color('green', '(relative)') if use_relative_affy else '')
                    for cgroup in treeutils.cgroups:
                        print '    %-12s  %15s  %s' % (pchoice, cgroup, ptvar)
                        arglist, kwargs = (args, action, metric, pchoice, cgroup, ptvar, ptlabel, args.final_plot_xvar), {'use_relative_affy' : use_relative_affy, 'metric_extra_str' : estr, 'debug' : args.debug}
                        if args.test:
                            make_plots(*arglist, **kwargs)
                        else:
                            procs.append(multiprocessing.Process(target=make_plots, args=arglist, kwargs=kwargs))
            if not args.test:
                utils.run_proc_functions(procs)
            for metric, estr in zip(args.plot_metrics, args.plot_metric_extra_strs):
                plotting.make_html(get_comparison_plotdir(metric, pchoice, extra_str=estr), n_columns=2)
        elif action == 'combine-plots':
            utils.prep_dir(get_comparison_plotdir('combined', None), subdirs=[pchoice], wildlings=['*.html', '*.svg'])
            cfg_list = set([ppair for mtmp in args.plot_metrics for ppair in lbplotting.single_lbma_cfg_vars(mtmp)])  # I don't think we care about the order
            cfg_list = lbplotting.add_use_relative_affy_stuff(cfg_list, include_relative_affy_plots=args.include_relative_affy_plots)
            for ptvar, ptlabel, use_relative_affy in cfg_list:
                print ptvar
                for cgroup in treeutils.cgroups:
                    print '  ', cgroup
                    make_plots(args, action, None, pchoice, cgroup, ptvar, ptlabel, args.final_plot_xvar, use_relative_affy=use_relative_affy)
            plotting.make_html(get_comparison_plotdir('combined', pchoice), n_columns=2)
        else:
            assert False
