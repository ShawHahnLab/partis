import copy
import pickle
from scipy import stats
import os
import sys
import numpy
import yaml
import json
import time
import warnings
import collections
import itertools

import utils
from hist import Hist
import treeutils
import plotting

# ----------------------------------------------------------------------------------------
# this name is terrible, but it's complicated and I can't think of a better one
def lb_metric_axis_cfg(metric_method=None):  # x axis variables against which we plot each lb metric (well, they're the x axis on the scatter plots, not the ptile plots)
    base_cfg = collections.OrderedDict([('lbi', [('affinity', 'affinity')]),
                                        ('lbr', [('n-ancestor', 'N ancestors')])  # , ('branch-length', 'branch length')])  # turning off branch length at least for now (for run time reasons)
    ])
    if metric_method is None:
        return base_cfg.items()
    elif metric_method in base_cfg:
        return [(m, cfg) for m, cfg in base_cfg.items() if m == metric_method]
    else:
        return [[metric_method, [('affinity', 'affinity')]]]  # e.g. shm

def meanmaxfcns(): return (('mean', lambda line, plotvals: numpy.mean(plotvals)), ('max', lambda line, plotvals: max(plotvals)))
def mean_of_top_quintile(vals):  # yeah, yeah could name it xtile and have another parameter, but maybe I won't actually need to change it
    frac = 0.2  # i.e. top quintile
    n_to_take = int(frac * len(vals))  # NOTE don't use numpy.percentile(), since affinity is fairly discrete-valued, which cause bad stuff (e.g. you don't take anywhere near the number of cells that you were trying to)
    return numpy.mean(sorted(vals)[len(vals) - n_to_take:])
mean_max_metrics = ['lbi', 'lbr', 'shm']
cluster_summary_cfg = collections.OrderedDict()
for k in mean_max_metrics:
    cluster_summary_cfg[k] = meanmaxfcns()
cluster_summary_cfg['affinity'] = (('top-quintile', lambda line, plotvals: mean_of_top_quintile(plotvals)), )
cluster_summary_cfg['fay-wu-h'] = (('fay-wu-h', lambda line, plotvals: -utils.fay_wu_h(line)), )
cluster_summary_cfg['consensus'] = (('consensus-shm', lambda line, plotvals: utils.hamming_distance(line['naive_seq'], treeutils.lb_cons_seq(line))), )
cluster_summary_cfg['is_leaf'] = (('x-dummy-x', lambda line, plotvals: None), )  # just to keep things from breaking, doesn't actually get used
def get_lbscatteraxes(lb_metric):
    return ['affinity', lb_metric]
def get_cluster_summary_strs(lb_metric):
    return ['%s-%s-vs-%s-%s' % (st1, get_lbscatteraxes(lb_metric)[0], st2, get_lbscatteraxes(lb_metric)[1]) for st1, st2 in itertools.product(cluster_summary_fcns, repeat=2)]  # all four combos and orderings of max/mean
def get_choice_groupings(lb_metric):  # TODO needs to be updated for non-lb methods
    # 'within-families': treat each cluster within each process/job separately (i.e. choosing cells only within each cluster)
    # 'among-families': treat each process/job as a whole (i.e. choose among all families in a process/job). Note that this means you can\'t separately adjust the number of families per job, and the number of families among which we choose cells (which is fine).
    cgroups = [('per-seq', ['within-families', 'among-families'])]
    if lb_metric in ['shm', 'lbi', 'lbr']:
        cgroups.append(('per-cluster', get_cluster_summary_strs(lb_metric)))
    return cgroups
per_seq_metrics = ('lbi', 'lbr', 'shm', 'consensus')
# per_clust_metrics = ('lbi', 'lbr', 'shm', 'fay-wu-h', 'consensus')  # don't need this atm since it's just all of them
mtitle_cfg = {'per-seq' : {'consensus' : '- distance to cons seq', 'shm' : '- N mutations', 'delta-lbi' : 'change in lb index'},
              'per-cluster' : {'fay-wu-h' : '- Fay-Wu H', 'consensus' : 'N mutations in cons seq', 'shm' : '- N mutations', 'affinity' : 'top quintile affinity'}}
def mtitlestr(pchoice, lbm, short=False):
    mtstr = mtitle_cfg[pchoice].get(lbm, treeutils.lb_metrics.get(lbm, lbm))
    if short and len(mtstr) > 13:
        mtstr = lbm
    return mtstr
# ----------------------------------------------------------------------------------------
metric_for_target_distance_labels = {
    'aa' : 'AA',
    'nuc' : 'nuc',
    'aa-sim-ascii' : 'ascii AA sim.',
    'aa-sim-blosum' : 'BLOSUM AA sim.',
}

# ----------------------------------------------------------------------------------------
def plot_bcr_phylo_selection_hists(histfname, plotdir, plotname, plot_all=False, n_plots=7, title='', xlabel=''):
    import joypy
    # ----------------------------------------------------------------------------------------
    def plot_this_time(otime, numpyhists):
        if plot_all:
            return True
        if otime == 0:
            return False
        if otime in (len(numpyhists),):
            return True
        if otime % max(1, int(len(numpyhists) / float(n_plots))) == 0:
            return True
        return False
    # ----------------------------------------------------------------------------------------
    def get_hists(hfname):
        with open(hfname) as runstatfile:
            numpyhists = pickle.load(runstatfile)
        xmin, xmax = None, None
        hists, ylabels, xtralabels = [], [], []
        for ihist in range(len(numpyhists)):
            nphist = numpyhists[ihist]  # numpy.hist is two arrays: [0] is bin counts, [1] is bin x values (not sure if low, high, or centers)
            obs_time = ihist  #  + 1  # I *think* it's right without the 1 (although I guess it's really a little arbitrary)
            if not plot_this_time(obs_time, numpyhists):
                continue
            if nphist is None:  # time points at which we didn't sample
                hists.append(None)
                ylabels.append(None)
                xtralabels.append(None)
                continue
            bin_contents, bin_edges = nphist
            assert len(bin_contents) == len(bin_edges) - 1
            # print ' '.join('%5.1f' % c for c in bin_contents)
            # print ' '.join('%5.1f' % c for c in bin_edges)
            hist = Hist(len(bin_edges) - 1, bin_edges[0], bin_edges[-1])
            for ibin in range(len(bin_edges) - 1):  # nphist indexing, not Hist indexing
                lo_edge = bin_edges[ibin]
                hi_edge = bin_edges[ibin + 1]
                xmin = lo_edge if xmin is None else min(xmin, lo_edge)
                xmax = hi_edge if xmax is None else max(xmax, hi_edge)
                bin_center = (hi_edge + lo_edge) / 2.
                for _ in range(bin_contents[ibin]):
                    hist.fill(bin_center)
            hists.append(hist)
            ylabels.append('%d' % obs_time)
            xtralabels.append('(%.1f, %.0f)' % (hist.get_mean(), hist.integral(include_overflows=True)))

        hists, ylabels, xtralabels = zip(*[(h, yl, xl) for h, yl, xl in zip(hists, ylabels, xtralabels) if h is not None])  # remove None time points
        return hists, ylabels, xtralabels, xmin, xmax

    # ----------------------------------------------------------------------------------------
    all_hists, all_ylabels, all_xtralabels, xmin, xmax = get_hists(histfname)  # these xmin, xmax are the actual (ORd) bounds of the histograms (whereas below we also get the ranges that around filled)
    if sum(h.integral(include_overflows=True) for h in all_hists) == 0:
        print '  %s no/empty hists in %s' % (utils.color('yellow', 'warning'), histfname)
        return
    jpdata = []
    for hist in all_hists:
        jpdata.append([x for x, y in zip(hist.get_bin_centers(), hist.bin_contents) for _ in range(int(y)) if x > xmin and x < xmax])  # NOTE this is repeating the 'for _ in range()' in the fcn above, but that's because I used to be actually using the Hist()s, and maybe I will again

    fbin_xmins, fbin_xmaxs = zip(*[h.get_filled_bin_xbounds(extra_pads=2) for h in all_hists])
    xmin_filled, xmax_filled = min(fbin_xmins), max(fbin_xmaxs)

    pre_fig, pre_ax = plotting.mpl_init()  # not sure to what extent these really get used after joypy is done with things
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')  # i don't know why it has to warn me that it's clearing the fig/ax I'm passing in, and I don't know how else to stop it
        fig, axes = joypy.joyplot(jpdata, labels=all_ylabels, fade=True, hist=True, overlap=0.5, ax=pre_ax, x_range=(xmin_filled, xmax_filled), bins=int(xmax_filled - xmin_filled), xlabelsize=15) #, ylabelsize=15)
    # xtextpos = 0.85 * (xmax_filled - xmin_filled) + xmin_filled  # this is from before I found transform=ax.transAxes, but I don't want to remove it yet
    fsize = 15
    for ax, lab in zip(axes, all_xtralabels):
        ax.text(0.85, 0.2, lab, fontsize=fsize, transform=ax.transAxes)
    fig.text(0.03, 0.9, 'generation', fontsize=fsize)
    fig.text(0.8, 0.87, '(mean, N cells)', fontsize=fsize)
    # NOTE do *not* set your own x ticks/labels in the next line, since they'll be in the wrong place (i.e. not the same as where joypy puts them) (also note, the stupid y labels don't work, but setting them on the joyplot axes also doesn't work)
    plotting.mpl_finish(pre_ax, plotdir, plotname, title=title, xlabel=xlabel) #, ylabel='generation') #, leg_loc=(0.7, 0.45)) #, xbounds=(minfrac*xmin, maxfrac*xmax), ybounds=(-0.05, 1.05), log='x', xticks=xticks, xticklabels=[('%d' % x) for x in xticks], leg_loc=(0.8, 0.55 + 0.05*(4 - len(plotvals))), leg_title=leg_title, title=title)

# ----------------------------------------------------------------------------------------
def plot_bcr_phylo_kd_vals(plotdir, event):
    kd_changes = []
    dtree = treeutils.get_dendro_tree(treestr=event['tree'])
    for node in dtree.preorder_internal_node_iter():
        if node.taxon.label not in event['unique_ids']:
            continue
        inode = event['unique_ids'].index(node.taxon.label)
        node_affinity = event['affinities'][inode]
        for child in node.child_nodes():
            if child.taxon.label not in event['unique_ids']:
                continue
            ichild = event['unique_ids'].index(child.taxon.label)
            child_affinity = event['affinities'][ichild]
            kd_changes.append(1./child_affinity - 1./node_affinity)

    if len(kd_changes) > 0:
        hist = Hist(30, min(kd_changes), max(kd_changes))
        for val in kd_changes:
            hist.fill(val)
        fig, ax = plotting.mpl_init()
        hist.mpl_plot(ax, square_bins=True, errors=False)  #remove_empty_bins=True)
        plotname = 'kd-changes'
        plotting.mpl_finish(ax, plotdir,  plotname, xlabel='parent-child kd change', ylabel='branches', log='y') #, xbounds=(minfrac*xmin, maxfrac*xmax), ybounds=(-0.05, 1.05), log='x', xticks=xticks, xticklabels=[('%d' % x) for x in xticks], leg_loc=(0.8, 0.55 + 0.05*(4 - len(plotvals))), leg_title=leg_title, title=title)

    plotvals = {'shm' : [], 'kd_vals' : []}
    for iseq, uid in enumerate(event['unique_ids']):
        plotvals['shm'].append(event['n_mutations'][iseq])
        plotvals['kd_vals'].append(1. / event['affinities'][iseq])
    # new_cmap = plotting.truncate_colormap(plt.cm.Blues, 0, 1)
    # ax.hexbin(kd_changes, shms, gridsize=25, cmap=plt.cm.Blues) #, info['ccf_under'][meth], label='clonal fraction', color='#cc0000', linewidth=4)
    fig, ax = plotting.mpl_init()
    ax.scatter(plotvals['kd_vals'], plotvals['shm'], alpha=0.4)
    plotname = 'kd-vs-shm'
    plotting.mpl_finish(ax, plotdir, plotname, xlabel='Kd', ylabel='N mutations') #, xbounds=(minfrac*xmin, maxfrac*xmax), ybounds=(-0.05, 1.05), log='x', xticks=xticks, xticklabels=[('%d' % x) for x in xticks], leg_loc=(0.8, 0.55 + 0.05*(4 - len(plotvals))), leg_title=leg_title, title=title)

# ----------------------------------------------------------------------------------------
def plot_bcr_phylo_target_attraction(plotdir, event):  # plots of which sequences are going toward which targets
    from Bio.Seq import Seq

    fig, ax = plotting.mpl_init()

    # affinity vs stuff:
    # xvals = [1. / af for line in mutated_events for af in line['affinities']]
    # yvals = [nm for line in mutated_events for nm in line['n_mutations']]

    # # min distance to target:
    # yvals = [hd for line in mutated_events for hd in get_min_target_hdists(line['input_seqs'], line['target_seqs'])]
    # ax.scatter(xvals, yvals, alpha=0.65)

    hist = Hist(len(event['target_seqs']), -0.5, len(event['target_seqs']) - 0.5, value_list=event['nearest_target_indices'])
    hist.mpl_plot(ax, alpha=0.7, ignore_overflows=True)

    plotname = 'nearest-target-identities'
    plotting.mpl_finish(ax, plotdir, plotname, xlabel='index (identity) of nearest target sequence', ylabel='counts') #, xbounds=(minfrac*xmin, maxfrac*xmax), ybounds=(-0.05, 1.05), log='x', xticks=xticks, xticklabels=[('%d' % x) for x in xticks], leg_loc=(0.8, 0.55 + 0.05*(4 - len(plotvals))), leg_title=leg_title, title=title)

# ----------------------------------------------------------------------------------------
def plot_bcr_phylo_simulation(outdir, event, extrastr, metric_for_target_distance_label):
    utils.prep_dir(outdir + '/plots', wildlings=['*.csv', '*.svg'])

    plot_bcr_phylo_kd_vals(outdir + '/plots', event)
    plot_bcr_phylo_target_attraction(outdir + '/plots', event)

    plot_bcr_phylo_selection_hists('%s/%s_min_aa_target_hdists.p' % (outdir, extrastr), outdir + '/plots', 'min-aa-target-all-cells', title='all cells', xlabel='%s distance to nearest target seq' % metric_for_target_distance_label)
    plot_bcr_phylo_selection_hists('%s/%s_sampled_min_aa_target_hdists.p' % (outdir, extrastr), outdir + '/plots', 'min-aa-target-sampled-cells', plot_all=True, title='sampled cells (excluding ancestor sampling)', xlabel='%s distance to nearest target seq' % metric_for_target_distance_label)
    plot_bcr_phylo_selection_hists('%s/%s_n_mutated_nuc_hdists.p' % (outdir, extrastr), outdir + '/plots', 'n-mutated-nuc-all-cells', title='SHM all cells', xlabel='N nucleotide mutations to naive')

    plotting.make_html(outdir + '/plots')

# ----------------------------------------------------------------------------------------
def get_tree_from_line(line, is_true_line):
    if is_true_line:
        return line['tree']
    if 'tree-info' not in line:  # if 'tree-info' is missing, it should be because it's a small cluster in data that we skipped when calculating lb values
        return None
    return line['tree-info']['lb']['tree']

# ----------------------------------------------------------------------------------------
def plot_lb_scatter_plots(xvar, baseplotdir, lb_metric, lines_to_use, fnames=None, is_true_line=False, colorvar=None, only_overall=False, add_uids=False, n_per_row=4):  # <is_true_line> is there because we want the true and inferred lines to keep their trees in different places, because the true line just has the one, true, tree, while the inferred line could have a number of them (yes, this means I maybe should have called it the 'true-tree' or something)
    if fnames is None:
        fnames = []
    if len(fnames) == 0 or len(fnames[-1]) >= 2:
        fnames.append([])

    vtypes = [xvar, lb_metric]
    if add_uids: vtypes.append('uids')
    if colorvar is not None: vtypes.append(colorvar)
    plotdir = '%s/%s/%s-vs-%s' % (baseplotdir, lb_metric, lb_metric, xvar)
    utils.prep_dir(plotdir, wildlings='*.svg')
    plotvals = {x : [] for x in vtypes}
    basetitle = '%s %s vs %s' % ('true' if is_true_line else 'inferred', mtitlestr('per-seq', lb_metric, short=True), mtitlestr('per-seq', xvar, short=True).replace('- N', 'N'))  # here 'shm' the plain number of mutations, not 'shm' the non-lb metric, so we have to fiddle with the label in mtitle_cfg
    scatter_kwargs = {'xvar' : xvar, 'xlabel' : mtitlestr('per-seq', xvar).replace('- N', 'N'), 'colorvar' : colorvar, 'leg_loc' : (0.55, 0.75), 'log' : 'y' if lb_metric == 'lbr' else ''}
    sorted_lines = sorted(lines_to_use, key=lambda l: len(l['unique_ids']), reverse=True)
    for iclust, line in enumerate(sorted_lines):  # get depth/n_mutations for each node
        iclust_plotvals = {x : [] for x in vtypes}
        if colorvar == 'is_leaf':
            dtree = treeutils.get_dendro_tree(treestr=get_tree_from_line(line, is_true_line))
            if dtree is None:
                continue
        if xvar == 'shm':
            def xvalfcn(i): return line['n_mutations'][i]
        elif xvar == 'consensus':
            cseq = treeutils.lb_cons_seq(line)
            def xvalfcn(i): return -utils.hamming_distance(cseq, line['seqs'][i])  # NOTE the consensus value of course is *not* in ['tree-info']['lb'], since we're making a plot of actual lb vs consensus
        else:
            assert False
        for iseq, uid in enumerate(line['unique_ids']):
            if lb_metric == 'lbr' and line['tree-info']['lb'][lb_metric][uid] == 0:  # lbr equals 0 should really be treated as None/missing
                continue
            iclust_plotvals[xvar].append(xvalfcn(iseq))
            iclust_plotvals[lb_metric].append(line['tree-info']['lb'][lb_metric][uid])
            if colorvar is not None:
                if colorvar == 'is_leaf':
                    node = dtree.find_node_with_taxon_label(uid)
                    colorval = node.is_leaf() if node is not None else None
                elif colorvar == 'affinity':
                    colorval = line['affinities'][iseq] if 'affinities' in line else None
                iclust_plotvals[colorvar].append(colorval)  # I think any uid in <line> should be in the tree, but may as well handle the case where it isn't
            if add_uids:
                iclust_plotvals['uids'].append(uid)  # use to add None here instead of <uid> if this node didn't have an affinity value, but that seems unnecessary, I can worry about uid config options later when I actually use the uid dots for something
        if not only_overall:
            title = '%s (%d observed, %d total)' % (basetitle, len(line['unique_ids']), len(line['tree-info']['lb'][lb_metric]))
            fn = plot_2d_scatter('%s-vs-%s-iclust-%d' % (lb_metric, xvar, iclust), plotdir, iclust_plotvals, lb_metric, treeutils.lb_metrics[lb_metric], title, **scatter_kwargs)
        assert len(set([len(plotvals[vt]) for vt in plotvals])) == 1  # make sure all of them are the same length
        for vtype in [vt for vt in plotvals if vt != 'uids']:
            plotvals[vtype] += iclust_plotvals[vtype]
    fn = plot_2d_scatter('%s-vs-%s-all-clusters' % (lb_metric, xvar), plotdir, plotvals, lb_metric, treeutils.lb_metrics[lb_metric], '%s (all clusters)' % basetitle, **scatter_kwargs)
    fnames[-1].append(fn)

# ----------------------------------------------------------------------------------------
def plot_lb_distributions(baseplotdir, lines_to_use, is_true_line=False, fnames=None, metric_method=None, only_overall=False, affy_key='affinities', n_per_row=4):
    def make_hist(plotvals, n_total, n_skipped, iclust=None, affinities=None):
        if len(plotvals) == 0:
            return
        hist = Hist(30, min(plotvals), max(plotvals), value_list=plotvals)
        fig, ax = plotting.mpl_init()
        hist.mpl_plot(ax) #, square_bins=True, errors=False)
        fig.text(0.7, 0.8, 'mean %.3f' % numpy.mean(plotvals), fontsize=15)
        fig.text(0.7, 0.75, 'max %.3f' % max(plotvals), fontsize=15)
        if affinities is not None:
            fig.text(0.38, 0.88, 'mean/max affinity: %.4f/%.4f' % (numpy.mean(affinities), max(affinities)), fontsize=15)
        plotname = '%s-%s' % (lb_metric, str(iclust) if iclust is not None else 'all-clusters')
        leafskipstr = ', skipped %d leaves' % n_skipped if n_skipped > 0 else ''  # ok they're not necessarily leaves, but almost all of them are leaves (and not really sure how a non-leaf could get zero, but some of them seem to)
        fn = plotting.mpl_finish(ax, plotdir, plotname, xlabel=lb_label, log='y', ylabel='counts', title='%s %s  (size %d%s)' % ('true' if is_true_line else 'inferred', mtitlestr('per-seq', lb_metric, short=True), n_total, leafskipstr))
        if iclust is None:
            fnames[-1].append(fn)
        elif iclust < n_per_row:  # i.e. only put one row's worth in the html
            tmpfnames.append(fn)

    sorted_lines = sorted([l for l in lines_to_use if 'tree-info' in l], key=lambda l: len(l['unique_ids']), reverse=True)  # if 'tree-info' is missing, it should be because it's a small cluster we skipped when calculating lb values
    if fnames is None:  # no real effect (except not crashing) since we're not returning it any more
        fnames = []
    if len(fnames) < 1 or len(fnames) >= 4:
        fnames.append([])
    tmpfnames = []

    mlist = treeutils.lb_metrics.items() if metric_method is None else [(metric_method, mtitlestr('per-seq', metric_method))]
    for lb_metric, lb_label in mlist:
        plotvals = []
        n_total_skipped_leaves = 0
        plotdir = '%s/%s/distributions' % (baseplotdir, lb_metric)
        utils.prep_dir(plotdir, wildlings=['*.svg'])
        for iclust, line in enumerate(sorted_lines):
            lbfo = line['tree-info']['lb'][lb_metric]  # NOTE this contains any ancestor nodes that the phylogenetic program has in the tree, but that aren't in <line['unique_ids']>
            if is_true_line:
                iclust_plotvals = [lbfo[u] for u in line['unique_ids'] if u in lbfo]  # for the true plots, we *don't* want to include any inferred ancestor nodes that weren't actually sampled, since we don't have affinity info for them, and it'd make it look like there's a mismatch between these distributions and the lb vs affinity plots (which won't have them)
            else:
                iclust_plotvals = lbfo.values()  # whereas for real data, we want to include the inferred ancestor nodes for which we don't have sequences (although I guess in most cases where we're really interested in them, we would've used a phylogenetics program that also inferred their sequences, so they'd presumably have been added to <line['unique_ids']>)
            cluster_size = len(iclust_plotvals)  # i.e. including leaves
            if lb_metric == 'lbr':
                iclust_plotvals = [v for v in iclust_plotvals if v > 0.]  # don't plot the leaf values, they just make the plot unreadable
            if not only_overall:
                affinities = line[affy_key] if affy_key in line else None
                make_hist(iclust_plotvals, cluster_size, cluster_size - len(iclust_plotvals), iclust=iclust, affinities=affinities)
            plotvals += iclust_plotvals
            n_total_skipped_leaves += cluster_size - len(iclust_plotvals)
        make_hist(plotvals, len(plotvals) + n_total_skipped_leaves, n_total_skipped_leaves)

    # TODO can't be bothered to get this to work with the _vs_shm (above) a.t.m.
    # fnames.append(tmpfnames)

# ----------------------------------------------------------------------------------------
def make_lb_affinity_joyplots(plotdir, lines, lb_metric, fnames=None, n_clusters_per_joy_plot=25, n_max_joy_plots=25, n_plots_per_row=4):
    if fnames is not None:
        if len(fnames) == 0 or len(fnames[-1]) >= n_plots_per_row:
            fnames.append([])
    partition = utils.get_partition_from_annotation_list(lines)
    annotation_dict = {':'.join(l['unique_ids']) : l for l in lines}
    sorted_clusters = sorted(partition, key=lambda c: mean_of_top_quintile(annotation_dict[':'.join(c)]['affinities']), reverse=True)
    sorted_cluster_groups = [sorted_clusters[i : i + n_clusters_per_joy_plot] for i in range(0, len(sorted_clusters), n_clusters_per_joy_plot)]
    repertoire_size = sum([len(c) for c in sorted_clusters])
    max_affinity = max([a for c in sorted_clusters for a in annotation_dict[':'.join(c)]['affinities']])  # it's nice to keep track of the max values over the whole repertoire so all plots can have the same max values
    max_lb_val = max([annotation_dict[':'.join(c)]['tree-info']['lb'][lb_metric][u] for c in sorted_clusters for u in c])  # NOTE don't use all the values in the dict in 'tree-info', since non-sampled sequences (i.e. usually intermediate ancestors) are in there
    if max_lb_val == 0.:  # at least atm, this means this is lbr on a family with no common ancestor sampling
        return
    print 'divided repertoire of size %d with %d clusters into %d cluster groups' % (repertoire_size, len(sorted_clusters), len(sorted_cluster_groups))
    iclustergroup = 0
    for subclusters in sorted_cluster_groups:
        if iclustergroup > n_max_joy_plots:
            continue
        title = 'affinity and %s (%d / %d)' % (treeutils.lb_metrics[lb_metric], iclustergroup + 1, len(sorted_cluster_groups))  # NOTE it's important that this denominator is still right even when we don't make plots for all the clusters (which it is, now)
        fn = plotting.make_single_joyplot(subclusters, annotation_dict, repertoire_size, plotdir, '%s-affinity-joyplot-%d' % (lb_metric, iclustergroup), x1key='affinities', x1label='affinity', x2key=lb_metric, x2label=treeutils.lb_metrics[lb_metric],
                                          global_max_vals={'affinities' : max_affinity, lb_metric : max_lb_val}, title=title)  # note that we can't really add cluster_indices> like we do in partitionplotter.py, since (i think?) the only place there's per-cluster plots we'd want to correspond to is in the bcr phylo simulation dir, which has indices unrelated to anything we're sorting by here, and which we can't reconstruct
        if fnames is not None:
            if len(fnames[-1]) > n_plots_per_row:
                fnames.append([])
            fnames[-1].append(fn)
        iclustergroup += 1

# ----------------------------------------------------------------------------------------
def plot_2d_scatter(plotname, plotdir, plotvals, yvar, ylabel, title, xvar='affinity', xlabel='affinity', colorvar=None, log='', leg_loc=None, warn_text=None, markersize=15):
    leafcolors = {'leaf' : '#006600', 'internal' : '#2b65ec'}  # green, blue
    if len(plotvals[xvar]) == 0:
        # print '    no %s vs affy info' % yvar
        return '%s/%s.svg' % (plotdir, plotname)
    fig, ax = plotting.mpl_init()
    if colorvar is None:
        ax.scatter(plotvals[xvar], plotvals[yvar], alpha=0.4)
    else:
        if colorvar == 'is_leaf':
            colorfcn = lambda x: leafcolors['leaf' if x else 'internal']
            alpha = 0.4
        else:
            smap = plotting.get_normalized_scalar_map(plotvals[colorvar], 'viridis')
            colorfcn = lambda x: plotting.get_smap_color(smap, None, val=x)
            alpha = 0.8
        for x, y, cval in zip(plotvals[xvar], plotvals[yvar], plotvals[colorvar]):  # we used to do the leaf/internal plots as two scatter() calls, which might be faster? but I think what really takes the time is writing the svgs, so whatever
            ax.plot([x], [y], color=colorfcn(cval), marker='.', markersize=markersize, alpha=alpha)
    if 'uids' in plotvals:
        for xval, yval, uid in zip(plotvals[xvar], plotvals[yvar], plotvals['uids']):  # note: two ways to signal not to do this: sometimes we have 'uids' in the dict, but don't fill it (so the zip() gives an empty list), but sometimes we populate 'uids' with None values
            if uid is None:
                continue
            ax.plot([xval], [yval], color='red', marker='.', markersize=markersize)
            ax.text(xval, yval, uid, color='red', fontsize=8)

    if warn_text is not None:
        ax.text(0.6 * ax.get_xlim()[1], 0.75 * ax.get_ylim()[1], warn_text, fontsize=30, fontweight='bold', color='red')
    xmin, xmax = [mfcn(plotvals[xvar]) for mfcn in [min, max]]
    ymin, ymax = [mfcn(plotvals[yvar]) for mfcn in [min, max]]
    xbounds = xmin - 0.02 * (xmax - xmin), xmax + 0.02 * (xmax - xmin)
    if 'y' in log:
        ybounds = 0.75 * ymin, 1.3 * ymax
    else:
        ybounds = ymin - 0.03 * (ymax - ymin), ymax + 0.08 * (ymax - ymin)
    if yvar in ['shm', 'consensus']:
        ax.plot([xmin, xmax], [0, 0], linewidth=1, alpha=0.7, color='grey')
    leg_title, leg_prop = None, None
    if colorvar is not None:
        leg_loc = (0.1 if xvar in ['consensus', 'affinity'] else 0.7, 0.65)  # I think this is sometimes overriding the one that's passed in
        leg_prop = {'size' : 12}
        if colorvar == 'is_leaf':
            leg_iter = [(leafcolors[l], l) for l in ['leaf', 'internal']]
        elif colorvar == 'affinity':
            leg_title = colorvar
            cmin, cmax = [mfcn(plotvals[colorvar]) for mfcn in [min, max]]  # NOTE very similar to add_legend() in bin/plot-lb-tree.py
            n_entries = 4
            max_diff = (cmax - cmin) / float(n_entries - 1)
            leg_iter = [(colorfcn(v), '%.3f'%v) for v in list(numpy.arange(cmin, cmax + utils.eps, max_diff))]  # first value is exactly <cmin>, last value is exactly <cmax> (eps is to keep it from missing the last one)
        else:
            assert False
        for tcol, tstr in leg_iter:
            ax.plot([], [], color=tcol, label=tstr, marker='.', markersize=markersize, linewidth=0)

    fn = plotting.mpl_finish(ax, plotdir, plotname, title=title, xlabel=xlabel, ylabel=ylabel, xbounds=xbounds, ybounds=ybounds, log=log, leg_loc=leg_loc, leg_title=leg_title, leg_prop=leg_prop)
    return fn

# ----------------------------------------------------------------------------------------
def get_ptile_vals(lb_metric, plotvals, xvar, xlabel, ptile_range_tuple=(50., 100., 1.), dbgstr=None, affy_key_str='', debug=False):
    def get_final_xvar_vals(corr_xvals):  # for affinity we go one extra step and compare against percentiles, since it's not obvious looking at plain affinity numbers how good they are (whereas N ancestors and branch length we just want to be small)
        return corr_xvals if not xia else [stats.percentileofscore(plotvals[xvar], caffy, kind='weak') for caffy in corr_xvals]  # affinity percentiles corresponding to each of these affinities  # NOTE this is probably really slow (especially because I'm recalculating things I don't need to)
    # NOTE xvar and xlabel refer to the x axis on the scatter plot from which we make this ptile plot (i.e. are affinity, N ancestors, or branch length). On this ptile plot it's the y axis. (I tried calling it something else, but it was more confusing)
    xia = xvar == 'affinity'
    xkey = 'mean_%s_ptiles' % xvar
    tmp_ptvals = {'lb_ptiles' : [], xkey : [], 'perfect_vals' : []}  # , 'reshuffled_vals' : []}
    if len(plotvals[xvar]) == 0:
        return tmp_ptvals
    if debug:
        print '    getting ptile vals%s' % ('' if dbgstr is None else (' for %s' % utils.color('blue', dbgstr)))
        print '            %3s         N     mean    %s    |  perfect   perfect' % (lb_metric, 'mean   ' if xia else '')
        print '    ptile  threshold  taken   %s%-s %s|  N taken  mean %s'  % (affy_key_str.replace('relative-', 'r-'), 'affy' if xia else xlabel, '   affy ptile ' if xia else '', 'ptile' if xia else xlabel)
    sorted_xvals = sorted(plotvals[xvar], reverse=xia)
    for percentile in numpy.arange(*ptile_range_tuple):
        lb_ptile_val = numpy.percentile(plotvals[lb_metric], percentile)  # lb value corresponding to <percentile>
        corresponding_xvals = [xv for lb, xv in zip(plotvals[lb_metric], plotvals[xvar]) if lb > lb_ptile_val]  # x vals corresponding to lb greater than <lb_ptile_val> (i.e. the x vals that you'd get if you took all the lb values greater than that)
        if len(corresponding_xvals) == 0:
            if debug:
                print '   %5.0f    no vals' % percentile
            continue
        tmp_ptvals['lb_ptiles'].append(float(percentile))  # stupid numpy-specific float classes (I only care because I write it to a yaml file below)
        tmp_ptvals[xkey].append(float(numpy.mean(get_final_xvar_vals(corresponding_xvals))))

        # make a "perfect" line using the actual x values, as opposed to just a straight line (this accounts better for, e.g. the case where the top N affinities are all the same)
        n_to_take = len(corresponding_xvals)  # this used to be (in general) different than the number we took above, hence the weirdness/duplication (could probably clean up at this point)
        perfect_xvals = sorted_xvals[:n_to_take]
        tmp_ptvals['perfect_vals'].append(float(numpy.mean(get_final_xvar_vals(perfect_xvals))))

        if debug:
            v1str = ('%8.4f' % numpy.mean(corresponding_xvals)) if xia else ''
            f1str = '5.0f' if xia else '6.2f'
            f2str = '5.0f' if xia else ('8.2f' if xvar == 'n-ancestor' else '8.6f')
            print ('   %5.0f   %5.2f     %4d  %s  %'+f1str+'       | %4d    %-'+f2str) % (percentile, lb_ptile_val, len(corresponding_xvals), v1str, tmp_ptvals[xkey][-1], n_to_take, tmp_ptvals['perfect_vals'][-1])
        # old way of adding a 'no correlation' line:
        # # add a horizontal line at 50 to show what it'd look like if there was no correlation (this is really wasteful... although it does have a satisfying wiggle to it. Now using a plain flat line [below])
        # shuffled_lb_vals = copy.deepcopy(plotvals[lb_metric])
        # random.shuffle(shuffled_lb_vals)
        # NON_corresponding_xvals = [affy for lb, affy in zip(shuffled_lb_vals, plotvals[xvar]) if lb > lb_ptile_val]
        # NON_corr_affy_ptiles = [stats.percentileofscore(plotvals[xvar], caffy, kind='weak') for caffy in NON_corresponding_xvals]
        # tmp_ptvals['reshuffled_vals'].append(numpy.mean(NON_corr_affy_ptiles))
    return tmp_ptvals

# ----------------------------------------------------------------------------------------
def make_ptile_plot(tmp_ptvals, xvar, plotdir, plotname, plotvals=None, affy_key=None, xlabel=None, ylabel='?', title=None, fnames=None, ptile_range_tuple=(50., 100., 1.), true_inf_str='?', n_clusters=None):
    fig, ax = plotting.mpl_init()
    xia = xvar == 'affinity'
    xmean = 50 if xia else numpy.mean(plotvals[xvar])  # NOTE for the latter case, this is mean of "xvar", which is the x axis on the scatter plot, but here it's the y axis on the ptile plot
    xkey = 'mean_%s_ptiles' % xvar
    if xlabel is None:
        xlabel = xvar

    ax.plot(tmp_ptvals['lb_ptiles'], tmp_ptvals[xkey], linewidth=3, alpha=0.7)

    # lines corresponding to no correlation and perfect correlation to guide the eye
    bad_args = ((ax.get_xlim(), (xmean, xmean)), {'linewidth' : 3, 'alpha' : 0.7, 'color' : 'darkred', 'linestyle' : '--', 'label' : 'no correlation'})
    perf_args = ((tmp_ptvals['lb_ptiles'], tmp_ptvals['perfect_vals']), {'linewidth' : 3, 'alpha' : 0.7, 'color' : 'darkgreen', 'linestyle' : '--', 'label' : 'perfect correlation'})
    for (args, kwargs) in (perf_args, bad_args) if xia else (bad_args, perf_args):  # shenanigans are so their top/bottom ordering matches the actual lines
        ax.plot(*args, **kwargs)

    if xia:
        # ax.plot(ax.get_xlim(), [50 + 0.5 * x for x in ax.get_xlim()], linewidth=3, alpha=0.7, color='darkgreen', linestyle='--', label='perfect correlation')  # straight line
        # ax.plot(tmp_ptvals['lb_ptiles'], tmp_ptvals['reshuffled_vals'], linewidth=3, alpha=0.7, color='darkred', linestyle='--', label='no correlation')  # reshuffled vals
        ybounds = (45, 102)
        leg_loc = (0.5, 0.2)
        xlabel = xlabel.replace('affinity', 'affinities')
        ptile_ylabel = 'mean percentile of\nresulting %s' % xlabel
    else:
        ymax = max([xmean] + tmp_ptvals[xkey] + tmp_ptvals['perfect_vals'])
        ybounds = (-0.02*ymax, 1.1*ymax)
        leg_loc = (0.5, 0.6)
        ptile_ylabel = 'mean %s\nsince affinity increase' % xlabel

    if n_clusters is not None and n_clusters > 1:
        fig.text(0.37, 0.88, 'choosing among %d families' % n_clusters, fontsize=17, fontweight='bold')  # , color='red'
        if affy_key is not None and 'relative' in affy_key:  # maybe I should just not make the plot, but then the html would look weird
            ax.text(0.6 * ax.get_xlim()[1], 0.75 * ax.get_ylim()[1], 'wrong/misleading', fontsize=30, fontweight='bold', color='red')
    fn = plotting.mpl_finish(ax, plotdir, plotname, xbounds=ptile_range_tuple, ybounds=ybounds, leg_loc=leg_loc,
                             title='potential %s thresholds (%s tree)' % (title if title is not None else ylabel, true_inf_str),
                             xlabel='%s threshold (percentile)' % ylabel,
                             ylabel=ptile_ylabel)
    if fnames is not None:
        fnames[-1].append(fn)

# ----------------------------------------------------------------------------------------
def plot_lb_vs_affinity(baseplotdir, lines, lb_metric, lb_label, ptile_range_tuple=(50., 100., 1.), is_true_line=False, n_per_row=4, affy_key='affinities', only_csv=False, fnames=None, add_uids=False, colorvar='is_leaf', debug=False):
    # ----------------------------------------------------------------------------------------
    def get_plotvals(line):
        plotvals = {vt : [] for vt in vtypes + ['uids']}
        if colorvar is not None and colorvar == 'is_leaf':
            dtree = treeutils.get_dendro_tree(treestr=get_tree_from_line(line, is_true_line))  # keeping this here to remind myself how to get the tree if I need it
        if affy_key not in line:
            return plotvals
        for uid, affy in [(u, a) for u, a in zip(line['unique_ids'], line[affy_key]) if a is not None]:
            plotvals['affinity'].append(affy)
            if lb_metric in per_seq_metrics:
                plotvals[lb_metric].append(line['tree-info']['lb'][lb_metric][uid])  # NOTE there's lots of entries in the lb info that aren't observed (i.e. aren't in line['unique_ids'])
            if add_uids:
                plotvals['uids'].append(uid)
            if colorvar is not None and colorvar == 'is_leaf':
                node = dtree.find_node_with_taxon_label(uid)
                plotvals['is_leaf'].append(node.is_leaf() if node is not None else None)
        return plotvals
    # ----------------------------------------------------------------------------------------
    def getplotdir(extrastr=''):
        return '%s/%s-vs%s-affinity%s' % (baseplotdir, lb_metric, affy_key_str, extrastr)
    # ----------------------------------------------------------------------------------------
    def icstr(iclust):
        return '-all-clusters' if iclust is None else '-iclust-%d' % iclust
    # ----------------------------------------------------------------------------------------
    def tmpstrs(iclust, vspstuff):
        lbstr, affystr, clstr = lb_metric, 'affinity', icstr(iclust)
        pchoice = 'per-seq' if vspstuff is None else 'per-cluster'
        xlabel, ylabel = '%s affinity' % affy_key_str.replace('-', ''), mtitlestr(pchoice, lb_metric)
        title = '%s on %s tree' % (mtitlestr(pchoice, lb_metric, short=True), true_inf_str)
        if affy_key_str != '':  # add 'relative-' at the start
            affystr = '%s-%s' % (affy_key_str, affystr)
        if vspstuff is not None:
            assert iclust is None
            lbstr = '%s-%s' % (vspstuff[lb_metric], lbstr)
            affystr = '%s-%s' % (vspstuff['affinity'], affystr)
            clstr = '-per-cluster'
            title += ' (per family)'
            xlabel = '%s %s' % (vspstuff['affinity'], xlabel)
            if lb_metric in mean_max_metrics:
                ylabel = '%s%s%s%s' % (vspstuff[lb_metric], ' ' if lb_metric in treeutils.lb_metrics else '(', ylabel, '' if lb_metric in treeutils.lb_metrics else ')')
        else:
            if iclust is None:
                title += ' (%d families together)' % len(lines)
        return lbstr, affystr, clstr, xlabel, ylabel, title
    # ----------------------------------------------------------------------------------------
    def tmpxlabel(iclust, vspstuff):
        _, _, _, xlabel, _, _ = tmpstrs(iclust, vspstuff)
        return xlabel
    # ----------------------------------------------------------------------------------------
    def tmpylabel(iclust, vspstuff):
        _, _, _, _, ylabel, _ = tmpstrs(iclust, vspstuff)
        return ylabel
    # ----------------------------------------------------------------------------------------
    def make_scatter_plot(plotvals, iclust=None, vspstuff=None):
        warn_text = 'wrong/misleading' if len(lines) > 1 and iclust is None and 'relative' in affy_key else None  # maybe I should just not make the plot, but then the html would look weird UPDATE stopped making the plot by default, but the warning is still a good idea if I start making it again
        lbstr, affystr, clstr, xlabel, ylabel, title = tmpstrs(iclust, vspstuff)
        plotname = '%s-vs-%s-%s-tree%s' % (lbstr, affystr, true_inf_str, clstr)
        fn = plot_2d_scatter(plotname, getplotdir(), plotvals, lb_metric, ylabel, title, xlabel=xlabel, colorvar=colorvar if vspstuff is None else None, warn_text=warn_text)
        if iclust is None: # or iclust < n_per_row:
            fnames[-1].append(fn)
    # ----------------------------------------------------------------------------------------
    def ptile_plotname(iclust=None, vspstuff=None):
        lbstr, affystr, clstr, _, _, _ = tmpstrs(iclust, vspstuff)
        return '%s-vs-%s-%s-tree-ptiles%s' % (lbstr, affystr, true_inf_str, clstr)
    # ----------------------------------------------------------------------------------------
    def getcorr(xvals, yvals):
        return numpy.corrcoef(xvals, yvals)[0, 1]
    # ----------------------------------------------------------------------------------------
    def getcorrkey(xstr, ystr):
        return '-vs-'.join([xstr, ystr])

    # ----------------------------------------------------------------------------------------
    if fnames is None:  # not much point since we're not returning it any more
        fnames = []
    fnames += [[], []]
    affy_key_str = '-relative' if 'relative' in affy_key else ''
    true_inf_str = 'true' if is_true_line else 'inferred'
    vtypes = get_lbscatteraxes(lb_metric)  # NOTE this puts relative affinity under the (plain) affinity key, which is kind of bad maybe i think probably
    if colorvar is not None:
        vtypes.append(colorvar)
    for estr in ['', '-ptiles']:
        utils.prep_dir(getplotdir(estr), wildlings=['*.svg', '*.yaml'])

    per_seq_plotvals = {vt : [] for vt in vtypes}  # plot values for choosing single seqs/cells (only among all clusters, since the iclust ones don't need to kept outside the cluster loop)
    per_clust_plotvals = {vt : {sn : [] for sn, _ in cluster_summary_cfg[vt]} for vt in vtypes}  # each cluster plotted as one point using a summary over its cells (e.g. max, mean) for affinity and lb
    ptile_vals = {'per-seq' : {}, 'per-cluster' : {}}  # 'per-seq': choosing single cells, 'per-cluster': choosing clusters; with subkeys in the former both for choosing sequences only within each cluster ('iclust-N', used later in cf-tree-metrics.py to average over all clusters in all processes) and for choosing sequences among all clusters together ('all-clusters')
    correlation_vals = {'per-seq' : {}, 'per-cluster' : {}}
    if debug:
        print '                        %8s         %8s' % tuple(vtypes[:2])
        print '  iclust   size  %8s  %8s  %8s  %8s' % tuple(st for _ in range(2) for st in cluster_summary_fcns)
    for iclust, line in enumerate(lines):
        if debug:
            print '  %3d    %4d   ' % (iclust, len(line['unique_ids'])),
        iclust_plotvals = get_plotvals(line)  # if it's not in <per_seq_metrics> we still need the affinity values
        if lb_metric in per_seq_metrics:
            if iclust_plotvals[lb_metric].count(0.) == len(iclust_plotvals[lb_metric]):  # i.e. (atm) lbr on family that's only leaves (it would be nice to have a more sensible way to do this, but I guess it's not really a big deal since I think we're done sampling only leaves)
                continue
            for vt in vtypes:
                per_seq_plotvals[vt] += iclust_plotvals[vt]
        for vt in vtypes[:2]:
            for sname, sfcn in cluster_summary_cfg[vt]:
                per_clust_plotvals[vt][sname].append(sfcn(line, iclust_plotvals[vt]))
                if debug:
                    print '    %5.3f' % per_clust_plotvals[vt][sname][-1],
        if debug:
            print ''
        if lb_metric not in per_seq_metrics:
            continue
        iclust_ptile_vals = get_ptile_vals(lb_metric, iclust_plotvals, 'affinity', 'affinity', dbgstr='iclust %d'%iclust, affy_key_str=affy_key_str, debug=debug)
        ptile_vals['per-seq']['iclust-%d'%iclust] = iclust_ptile_vals
        correlation_vals['per-seq']['iclust-%d'%iclust] = {getcorrkey(*vtypes[:2]) : getcorr(*[iclust_plotvals[vt] for vt in vtypes[:2]])}
        if not only_csv and len(iclust_plotvals['affinity']) > 0:
            make_scatter_plot(iclust_plotvals, iclust=iclust)
            make_ptile_plot(iclust_ptile_vals, 'affinity', getplotdir('-ptiles'), ptile_plotname(iclust=iclust), affy_key=affy_key,
                            ylabel=tmpylabel(iclust, None), title=mtitlestr('per-seq', lb_metric, short=True), true_inf_str=true_inf_str)

    if lb_metric in per_seq_metrics:
        if per_seq_plotvals[lb_metric].count(0.) == len(per_seq_plotvals[lb_metric]):
            return
        correlation_vals['per-seq']['all-clusters'] = {getcorrkey(*vtypes[:2]) : getcorr(*[per_seq_plotvals[vt] for vt in vtypes[:2]])}

    for sn1, sfcn1 in cluster_summary_cfg[vtypes[0]]:  # I tried really hard to work out a way to get this in one (cleaner) loop
        for sn2, sfcn2 in cluster_summary_cfg[vtypes[1]]:
            vspairs = zip(vtypes[:2], (sn1, sn2))  # assign this (sn1, st2) combo to lb and affinity based on their order in <vtypes> (although now that we're using a double loop this is even weirder)
            vspdict = {v : s for v, s in vspairs}  # need to also access it by key
            tmpvals = {vt : per_clust_plotvals[vt][sn] for vt, sn in vspairs}  # e.g. 'affinity' : <max affinity value list>, 'lbi' : <mean lbi value list>
            tkey = getcorrkey('%s-affinity%s' % (vspdict['affinity'], affy_key_str), '%s-%s' % (vspdict[lb_metric], lb_metric))  # can't use <vtypes> because of the stupid <affy_key_str>
            correlation_vals['per-cluster'][tkey] = getcorr(tmpvals['affinity'], tmpvals[lb_metric])
            tmp_ptile_vals = get_ptile_vals(lb_metric, tmpvals, 'affinity', 'affinity', affy_key_str=affy_key_str, debug=debug)
            ptile_vals['per-cluster'][tkey] = tmp_ptile_vals
            if not only_csv:
                make_scatter_plot(tmpvals, vspstuff=vspdict)
                make_ptile_plot(tmp_ptile_vals, 'affinity', getplotdir('-ptiles'), ptile_plotname(vspstuff=vspdict), affy_key=affy_key,
                                xlabel=tmpxlabel(None, vspdict), ylabel=tmpylabel(None, vspdict), title=mtitlestr('per-cluster', lb_metric, short=True), fnames=fnames, true_inf_str=true_inf_str)

    if lb_metric in per_seq_metrics:
        ptile_vals['per-seq']['all-clusters'] = get_ptile_vals(lb_metric, per_seq_plotvals, 'affinity', 'affinity', affy_key_str=affy_key_str, debug=debug)  # choosing single cells from from every cell from every cluster together
        if not only_csv and len(per_seq_plotvals[lb_metric]) > 0:
            fnames.append([])
            make_scatter_plot(per_seq_plotvals)
            make_ptile_plot(ptile_vals['per-seq']['all-clusters'], 'affinity', getplotdir('-ptiles'), ptile_plotname(), affy_key=affy_key,
                            ylabel=tmpylabel(None, None), title=mtitlestr('per-seq', lb_metric, short=True), fnames=fnames, true_inf_str=true_inf_str, n_clusters=len(lines))
    with open('%s/%s.yaml' % (getplotdir('-ptiles'), ptile_plotname()), 'w') as yfile:
        yamlfo = {'percentiles' : ptile_vals, 'correlations' : correlation_vals}
        json.dump(yamlfo, yfile)

# ----------------------------------------------------------------------------------------
def plot_lb_vs_ancestral_delta_affinity(baseplotdir, lines, lb_metric, lb_label, ptile_range_tuple=(50., 100., 1.), is_true_line=False, min_affinity_change=1e-6, n_max_steps=15, only_csv=False, fnames=None, n_per_row=4, debug=False):
    # plot lb[ir] vs both number of ancestors and branch length to nearest affinity decrease (well, decrease as you move upwards in the tree/backwards in time)
    # ----------------------------------------------------------------------------------------
    def check_affinity_changes(affinity_changes):
        affinity_changes = sorted(affinity_changes)
        if debug:
            print '    checking affinity changes for negative values and unexpected variation: %s' % ' '.join(['%.4f' % a for a in affinity_changes])  # well, the variation isn't really unexpected, but it's worth keeping in mind
        if len(affinity_changes) == 0:
            if debug:
                print '      %s empty affinity changes list' % utils.color('yellow', 'note')
            return
        if any(a < 0. for a in affinity_changes):
            print '  %s negative affinity changes in %s' % (utils.color('red', 'error'), ' '.join(['%.4f' % a for a in affinity_changes]))
        max_diff = affinity_changes[-1] - affinity_changes[0]
        # if abs(max_diff) / numpy.mean(affinity_changes) > 0.2:  # this is almost always true, which is fine, and I don't really plan on doing anything to change it soon (it would be nice to at some point use a performance metric gives us credit for differential prediction of different affinity change magnitudes, but oh well)
        #     print'      %s not all affinity increases were the same size (min: %.4f   max: %.4f   abs(diff) / mean: %.4f' % (utils.color('yellow', 'warning'), affinity_changes[0], affinity_changes[-1], abs(max_diff) / numpy.mean(affinity_changes))
    # ----------------------------------------------------------------------------------------
    def get_n_ancestor_vals(node, dtree, line, affinity_changes):
        # find number of steps/ancestors to the nearest ancestor with lower affinity than <node>'s
        #   - also finds the corresponding distance, which is to the lower end of the branch containing the corresponding affinity-increasing mutation
        #   - this is chosen so that <n_steps> and <branch_len> are both 0 for the node at the bottom of a branch on which affinity increases, and are *not* the distance *to* the lower-affinity node
        #   - because it's so common for affinity to get worse from ancestor to descendent, it's important to remember that here we are looking for the first ancestor with lower affinity than the node in question, which is *different* to looking for the first ancestor that has lower affinity than one of its immediate descendents (which we could also plot, but it probably wouldn't be significantly different to the metric performance, since for the metric performance we only really care about the left side of the plot, but this only affects the right side)
        #   - <min_affinity_change> is just to eliminate floating point precision issues (especially since we're deriving affinity by inverting kd) (note that at least for now, and with default settings, the affinity changes should all be pretty similar, and not small)
        this_affinity = utils.per_seq_val(line, 'affinities', node.taxon.label)
        if debug:
            print '     %12s %12s %8s %9.4f' % (node.taxon.label, '', '', this_affinity)
    
        ancestor_node = node
        chosen_ancestor_affinity = None
        n_steps, branch_len  = 0, 0.
        while n_steps < n_max_steps:  # note that if we can't find an ancestor with worse affinity, we don't plot the node
            if ancestor_node is dtree.seed_node:
                break
            ancestor_distance = ancestor_node.edge_length  # distance from current <ancestor_node> to its parent (who in the next line becomes <ancestor_node>)
            ancestor_node = ancestor_node.parent_node  #  move one more step up the tree
            ancestor_uid = ancestor_node.taxon.label
            if ancestor_uid not in line['unique_ids']:
                print '    %s ancestor %s of %s not in true line' % (utils.color('yellow', 'warning'), ancestor_uid, node.taxon.label)
                break
            ancestor_affinity = utils.per_seq_val(line, 'affinities', ancestor_uid)
            if this_affinity - ancestor_affinity > min_affinity_change:  # if we found an ancestor with lower affinity, we're done
                chosen_ancestor_affinity = ancestor_affinity
                affinity_changes.append(this_affinity - ancestor_affinity)
                break
            if debug:
                print '     %12s %12s %8.4f %9.4f%s' % ('', ancestor_uid, branch_len, ancestor_affinity, utils.color('green', ' x') if ancestor_node is dtree.seed_node else '')
            n_steps += 1
            branch_len += ancestor_distance
    
        if chosen_ancestor_affinity is None:  # couldn't find ancestor with lower affinity
            return None, None
        if debug:
            print '     %12s %12s %8.4f %9.4f  %s%-9.4f' % ('', ancestor_uid, branch_len, chosen_ancestor_affinity, utils.color('red', '+'), this_affinity - chosen_ancestor_affinity)
        return n_steps, branch_len
    # ----------------------------------------------------------------------------------------
    def get_plotvals(line, xvar):
        plotvals = {vt : [] for vt in [lb_metric, xvar]}  # , 'uids']}
        dtree = treeutils.get_dendro_tree(treestr=line['tree'])
        affinity_changes = []
        for uid in line['unique_ids']:
            node = dtree.find_node_with_taxon_label(uid)
            if node is dtree.seed_node:  # root doesn't have any ancestors
                continue
            lbval = line['tree-info']['lb'][lb_metric][uid]  # NOTE there's lots of entries in the lb info that aren't observed (i.e. aren't in line['unique_ids'])
            if lb_metric == 'lbr' and lbval == 0:  # lbr equals 0 should really be treated as None/missing
                continue
            n_steps, branch_len = get_n_ancestor_vals(node, dtree, line, affinity_changes)  # also adds to <affinity_changes>
            if n_steps is None:
                continue
            plotvals[xvar].append(n_steps if xvar == 'n-ancestor' else branch_len)
            plotvals[lb_metric].append(lbval)
            # plotvals['uids'].append(uid)
        check_affinity_changes(affinity_changes)
        return plotvals

    # ----------------------------------------------------------------------------------------
    def getplotdir(xvar, extrastr=''):
        return '%s/%s-vs-%s%s' % (baseplotdir, lb_metric, xvar, extrastr)
    # ----------------------------------------------------------------------------------------
    def icstr(iclust):
        return '-all-clusters' if iclust is None else '-iclust-%d' % iclust
    # ----------------------------------------------------------------------------------------
    def make_scatter_plot(plotvals, xvar, iclust=None):
        title = '%s on %s tree%s' % (mtitlestr('per-seq', lb_metric, short=True), true_inf_str, (' (%d families together)' % len(lines)) if iclust is None else '')
        fn = plot_2d_scatter('%s-vs-%s-%s-tree%s' % (lb_metric, xvar, true_inf_str, icstr(iclust)), getplotdir(xvar), plotvals, lb_metric, lb_label, title, xvar=xvar, xlabel='%s since affinity increase' % xlabel, log='y' if lb_metric == 'lbr' else '')
        if iclust is None: # or iclust < n_per_row:
            fnames[-1].append(fn)
    # ----------------------------------------------------------------------------------------
    def ptile_plotname(xvar, iclust):
        return '%s-vs-%s-%s-tree-ptiles%s' % (lb_metric, xvar, true_inf_str, icstr(iclust))

    # ----------------------------------------------------------------------------------------
    if fnames is None:  # no real effect (except not crashing) since we're not returning it any more
        fnames = []
    if len(fnames) == 0 or len(fnames[-1]) >= 4:
        fnames += [[]]
    true_inf_str = 'true' if is_true_line else 'inferred'
    xvar_list = collections.OrderedDict([(xvar, xlabel) for metric, cfglist in lb_metric_axis_cfg('lbr') for xvar, xlabel in cfglist])
    for xvar, estr in itertools.product(xvar_list, ['', '-ptiles']):
        utils.prep_dir(getplotdir(xvar, extrastr=estr), wildlings=['*.svg', '*.yaml'])
    if debug:
        print 'finding ancestors with most recent affinity increases'
    for xvar, xlabel in xvar_list.items():
        per_seq_plotvals = {vt : [] for vt in [lb_metric, xvar]}  # , 'uids']}
        # not yet implemented: per_clust_plotvals = {st : {vt : [] for vt in vtypes} for st in cluster_summary_fcns}  # each cluster plotted as one point using a summary over its cells (max or mean) for affinity and lb
        ptile_vals = {'per-seq' : {}, 'per-cluster' : {}}  # 'per-seq': choosing single cells, 'per-cluster': choosing clusters; with subkeys in the former both for choosing sequences only within each cluster ('iclust-N', used later in cf-tree-metrics.py to average over all clusters in all processes) and for choosing sequences among all clusters together ('all-clusters')
        # not yet implemented: correlation_vals = {'per-seq' : {}, 'per-cluster' : {}}
        for iclust, line in enumerate(lines):
            if debug:
                if iclust == 0:
                    print ' %s' % utils.color('green', xvar)
                print '  %s' % utils.color('blue', 'iclust %d' % iclust)
                print '         node        ancestors  distance   affinity (%sX: change for chosen ancestor, %s: reached root without finding lower-affinity ancestor)' % (utils.color('red', '+'), utils.color('green', 'x'))
            iclust_plotvals = get_plotvals(line, xvar)
            for vtype in per_seq_plotvals:
                per_seq_plotvals[vtype] += iclust_plotvals[vtype]
            iclust_ptile_vals = get_ptile_vals(lb_metric, iclust_plotvals, xvar, xlabel, dbgstr='iclust %d'%iclust, debug=debug)
            ptile_vals['per-seq']['iclust-%d'%iclust] = iclust_ptile_vals
            if not only_csv and len(iclust_plotvals[xvar]) > 0:
                make_scatter_plot(iclust_plotvals, xvar, iclust=iclust)
                make_ptile_plot(iclust_ptile_vals, xvar, getplotdir(xvar, extrastr='-ptiles'), ptile_plotname(xvar, iclust), plotvals=iclust_plotvals,
                                xlabel=xlabel, ylabel=mtitlestr('per-seq', lb_metric), true_inf_str=true_inf_str)
        if not only_csv:
            make_scatter_plot(per_seq_plotvals, xvar)
        ptile_vals['per-seq']['all-clusters'] = get_ptile_vals(lb_metric, per_seq_plotvals, xvar, xlabel, dbgstr='all clusters', debug=debug)  # "averaged" might be a better name than "all", but that's longer
        with open('%s/%s.yaml' % (getplotdir(xvar, extrastr='-ptiles'), ptile_plotname(xvar, None)), 'w') as yfile:
            yamlfo = {'percentiles' : ptile_vals}
            json.dump(yamlfo, yfile)  # not adding the new correlation keys atm (like in the lb vs affinity fcn)
        if not only_csv and len(per_seq_plotvals[lb_metric]) > 0:
            make_ptile_plot(ptile_vals['per-seq']['all-clusters'], xvar, getplotdir(xvar, extrastr='-ptiles'), ptile_plotname(xvar, None), plotvals=per_seq_plotvals,
                            xlabel=xlabel, ylabel=mtitlestr('per-seq', lb_metric), fnames=fnames, true_inf_str=true_inf_str, n_clusters=len(lines))

# ----------------------------------------------------------------------------------------
def plot_true_vs_inferred_lb(plotdir, true_lines, inf_lines, lb_metric, lb_label, debug=False):
    plotvals = {val_type : {uid : l['tree-info']['lb'][lb_metric][uid] for l in lines for uid in l['unique_ids']}  # NOTE there's lots of entries in the lb info that aren't observed (i.e. aren't in line['unique_ids'])
                for val_type, lines in (('true', true_lines), ('inf', inf_lines))}
    common_uids = set(plotvals['true']) & set(plotvals['inf'])  # there should/may be a bunch of internal nodes in the simulation lines but not in the inferred lines, but otherwise they should have the same uids
    plotvals = {val_type : [plotvals[val_type][uid] for uid in common_uids] for val_type in plotvals}
    plotname = '%s-true-vs-inferred' % lb_metric
    fn = plot_2d_scatter(plotname, plotdir, plotvals, 'inf', '%s on inferred tree' % lb_metric.upper(), 'true vs inferred %s' % lb_metric.upper(), xvar='true', xlabel='%s on true tree' % lb_metric.upper())
    return [fn]

# ----------------------------------------------------------------------------------------
def get_lb_tree_cmd(treestr, outfname, lb_metric, affy_key, ete_path, subworkdir, metafo=None, tree_style=None):
    treefname = '%s/tree.nwk' % subworkdir
    metafname = '%s/meta.yaml' % subworkdir
    if not os.path.exists(subworkdir):
        os.makedirs(subworkdir)
    with open(treefname, 'w') as treefile:
        treefile.write(treestr)
    cmdstr = './bin/plot-lb-tree.py --treefname %s' % treefname
    if metafo is not None:
        with open(metafname, 'w') as metafile:
            yaml.dump(metafo, metafile)
        cmdstr += ' --metafname %s' % metafname
    cmdstr += ' --outfname %s' % outfname
    cmdstr += ' --lb-metric %s' % lb_metric
    cmdstr += ' --affy-key %s' % utils.reversed_input_metafile_keys[affy_key]
    # cmdstr += ' --lb-tau %f' % lb_tau
    if lb_metric == 'lbr':
        cmdstr += ' --log-lbr'
    if tree_style is not None:
        cmdstr += ' --tree-style %s' % tree_style
    cmdstr, _ = utils.run_ete_script(cmdstr, ete_path, return_for_cmdfos=True, tmpdir=subworkdir, extra_str='        ')

    return {'cmd_str' : cmdstr, 'workdir' : subworkdir, 'outfname' : outfname, 'workfnames' : [treefname, metafname]}

# ----------------------------------------------------------------------------------------
def plot_lb_trees(metric_methods, baseplotdir, lines, ete_path, base_workdir, is_true_line=False, tree_style=None):
    workdir = '%s/ete3-plots' % base_workdir
    plotdir = baseplotdir + '/trees'
    utils.prep_dir(plotdir, wildlings='*.svg')

    if not os.path.exists(workdir):
        os.makedirs(workdir)
    cmdfos = []
    for lb_metric in metric_methods:
        for iclust, line in enumerate(lines):  # note that <min_tree_metric_cluster_size> was already applied in treeutils
            treestr = get_tree_from_line(line, is_true_line)
            affy_key = 'affinities'  # turning off possibility of using relative affinity for now
            metafo = copy.deepcopy(line['tree-info']['lb'])  # NOTE there's lots of entries in the lb info that aren't observed (i.e. aren't in line['unique_ids'])
            if affy_key in line:  # either 'affinities' or 'relative_affinities'
                metafo[utils.reversed_input_metafile_keys[affy_key]] = {uid : affy for uid, affy in zip(line['unique_ids'], line[affy_key])}
            outfname = '%s/%s-tree-iclust-%d%s.svg' % (plotdir, lb_metric, iclust, '-relative' if 'relative' in affy_key else '')
            cmdfos += [get_lb_tree_cmd(treestr, outfname, lb_metric, affy_key, ete_path, '%s/sub-%d' % (workdir, len(cmdfos)), metafo=metafo, tree_style=tree_style)]

    start = time.time()
    utils.run_cmds(cmdfos, clean_on_success=True, shell=True, n_max_procs=10, proc_limit_str='plot-lb-tree.py')  # I'm not sure what the max number of procs is, but with 21 it's crashing with some of them not able to connect to the X server, and I don't see a big benefit to running them all at once anyways
    print '    made %d ete tree plots (%.1fs)' % (len(cmdfos), time.time() - start)

    os.rmdir(workdir)

# ----------------------------------------------------------------------------------------
def plot_per_mutation_lonr(plotdir, lines_to_use, reco_info):
    fig, ax = plotting.mpl_init()

    plotvals = {'lonr' : [], 'affinity_change' : []}
    for line in lines_to_use:
        true_affinities = {uid : reco_info[uid]['affinities'][0] for uid in line['unique_ids']}
        nodefos = line['tree-info']['lonr']['nodes']
        for lfo in line['tree-info']['lonr']['values']:
            if lfo['parent'] not in true_affinities:
                print '    %s parent \'%s\' not in true affinities, skipping lonr values' % (utils.color('red', 'warning'), lfo['parent'])
                continue
            if lfo['child'] not in true_affinities:
                print '    %s child \'%s\' not in true affinities, skipping lonr values' % (utils.color('red', 'warning'), lfo['child'])
                continue

            plotvals['lonr'].append(lfo['lonr'])
            plotvals['affinity_change'].append(true_affinities[lfo['child']] - true_affinities[lfo['parent']])

    ax.scatter(plotvals['affinity_change'], plotvals['lonr'], alpha=0.7) #, info['ccf_under'][meth], label='clonal fraction', color='#cc0000', linewidth=4)
    plotname = 'lonr-per-mut-vs-affinity'
    plotting.mpl_finish(ax, plotdir, plotname, xlabel='change in affinity', ylabel='LONR') #, xbounds=(minfrac*xmin, maxfrac*xmax), ybounds=(-0.05, 1.05), log='x', xticks=xticks, xticklabels=[('%d' % x) for x in xticks], leg_loc=(0.8, 0.55 + 0.05*(4 - len(plotvals))), leg_title=leg_title, title=title)

# ----------------------------------------------------------------------------------------
def plot_aggregate_lonr(plotdir, lines_to_use, reco_info, debug=False):
    fig, ax = plotting.mpl_init()
    plotvals = {'S' : [], 'NS' : []}
    for line in lines_to_use:
        for lfo in line['tree-info']['lonr']['values']:
            if lfo['synonymous']:
                plotvals['S'].append(lfo['lonr'])
            else:
                plotvals['NS'].append(lfo['lonr'])
    # ax.plot(plotvals['S'], label='S', linewidth=3, alpha=0.7)
    # ax.plot(plotvals['NS'], label='NS', linewidth=3, alpha=0.7)
    xmin, xmax = [mfcn([x for mtlist in plotvals.values() for x in mtlist]) for mfcn in (min, max)]
    hists = {mt : Hist(30, xmin, xmax, value_list=plotvals[mt], title=mt, xtitle='LONR', ytitle='mutations') for mt in plotvals}
    plotname = 'lonr-ns-vs-s'

    lonr_score = hists['NS'].get_mean() - hists['S'].get_mean()
    draw_no_root(hists['NS'], more_hists=[hists['S']], plotname=plotname, plotdir=plotdir, alphas=[0.7, 0.7], plottitle='NS - S: %.2f' % lonr_score, errors=True, remove_empty_bins=True)

    # for mt, hist in hists.items():
    #     hist.mpl_plot(ax, label=mt, remove_empty_bins=True)
    # plotting.mpl_finish(ax, plotdir, plotname, xlabel='LONR', ylabel='mutations') #, xbounds=(minfrac*xmin, maxfrac*xmax), ybounds=(-0.05, 1.05), log='x', xticks=xticks, xticklabels=[('%d' % x) for x in xticks], leg_loc=(0.8, 0.55 + 0.05*(4 - len(plotvals))), leg_title=leg_title, title=title)
