#!/usr/bin/env python
import argparse
import operator
import os
import sys
import yaml
import colored_traceback.always

# ----------------------------------------------------------------------------------------
def get_n_generations(ntl, tau):  # NOTE duplicates code in treeutils.get_max_lbi()
    return max(1, int(args.seq_len * tau * ntl))

# ----------------------------------------------------------------------------------------
def get_outfname(outdir):
    return '%s/vals.yaml' % outdir

# ----------------------------------------------------------------------------------------
def calc_max_lbi(args):
    if args.overwrite:
        raise Exception('not implemented')

    parsed_info = {}
    for lbt in args.lb_tau_list:

        gen_list = args.n_generations_list
        if gen_list is None:
            gen_list = [get_n_generations(ntl, lbt) for ntl in args.n_tau_lengths_list]
        print '   lb tau %.4f' % lbt
        print '      n gen: %s' % ' '.join(str(n) for n in gen_list)
        for n_gen in gen_list:

            # if ntl is not None:
            #     this_outdir = '%s/ XXX %s/n-tau-%.2f-lbt-%.4f' % (args.base_outdir, args.label, ntl, lbt)
            # elif n_gen is not None:
            this_outdir = '%s/lb-tau-optimization/%s/n_gen-%d-lbt-%.4f' % (args.base_outdir, args.label, n_gen, lbt)

            if os.path.exists(get_outfname(this_outdir)):
                if args.make_plots:
                    with open(get_outfname(this_outdir)) as outfile:
                        info = yaml.load(outfile)
                    if lbt not in parsed_info:
                        parsed_info[lbt] = {}
                    parsed_info[lbt][n_gen] = info['max']['lbi']
                else:
                    print '         output exists, skipping: %s' % get_outfname(this_outdir)
                continue

            if not os.path.exists(this_outdir):
                os.makedirs(this_outdir)

            # lbvals = treeutils.get_min_lbi(args.seq_len, args. XXX lb_tau)
            max_name, max_lbi, lbvals = treeutils.get_max_lbi(args.seq_len, lbt, n_generations=n_gen)
            # TODO maybe should write tree + lb values to file here?

            with open(get_outfname(this_outdir), 'w') as outfile:
                yaml.dump({'max' : {'name' : max_name, 'lbi' : max_lbi}}, outfile)

            plotdir = this_outdir + '/plots'
            utils.prep_dir(plotdir, wildlings='*.svg')
            cmdfos = [plotting.get_lb_tree_cmd(lbvals['tree'], '%s/tree.svg' % plotdir, 'lbi', 'affinities', args.ete_path, args.workdir, metafo=lbvals, tree_style='circular')]
            utils.run_cmds(cmdfos, clean_on_success=True, shell=True, debug='print')

    if args.make_plots:
        fig, ax = plotting.mpl_init()
        for lbt in sorted(parsed_info, reverse=True):
            n_gen_list, max_lbi_list = zip(*sorted(parsed_info[lbt].items(), key=operator.itemgetter(0)))
            ax.plot(n_gen_list, max_lbi_list, label='%.4f' % lbt, alpha=0.7, linewidth=4)
        plotting.mpl_finish(ax, args.base_outdir + '/lb-tau-optimization', 'tau-vs-n-gen-vs-max-lbi', xlabel='N generations', ylabel='Max LBI', leg_title='tau', leg_prop={'size' : 12}, leg_loc=(0.04, 0.67))

        # there's got to be a way to get a log plot without redoing everything, but I'm not sure what it is
        fig, ax = plotting.mpl_init()
        for lbt in sorted(parsed_info, reverse=True):
            n_gen_list, max_lbi_list = zip(*sorted(parsed_info[lbt].items(), key=operator.itemgetter(0)))
            ax.plot(n_gen_list, max_lbi_list, label='%.4f' % lbt, alpha=0.7, linewidth=4)
        plotting.mpl_finish(ax, args.base_outdir + '/lb-tau-optimization', 'tau-vs-n-gen-vs-max-lbi-log', log='y', xlabel='N generations', ylabel='Max LBI', leg_title='tau', leg_prop={'size' : 12}, leg_loc=(0.04, 0.67))

# ----------------------------------------------------------------------------------------
def get_bcr_phylo_outdir(varnames, vstr):
    assert len(varnames) == len(vstr)
    outdir = [args.base_outdir, args.label, 'bcr-phylo']
    for vn, vstr in zip(varnames, vstr):
        outdir.append('%s-%s' % (vn, vstr))
    return '/'.join(outdir)

# ----------------------------------------------------------------------------------------
def run_bcr_phylo(args):
    base_args = []
    varnames = []
    valfos, valstrs = [[]], [[]]  # first is the actual lists of values, second is strings, suitable for conversion to outdir and cmd str
    if len(args.carry_cap_list) > 1:
        varnames.append('carry-cap')
        valfos = [vlist + [cc] for vlist in valfos for cc in args.carry_cap_list]
        valstrs = [vlist + [str(cc)] for vlist in valstrs for cc in args.carry_cap_list]
    else:
        base_args.append('--carry-cap %d' % args.carry_cap_list[0])
    if len(args.n_sim_seqs_per_gen_list) > 1:
        varnames.append('n-sim-seqs-per-gen')
        valfos = [vlist + [nlist] for vlist in valfos for nlist in args.n_sim_seqs_per_gen_list]
        valstrs = [vlist + [':'.join(str(n) for n in nlist)] for vlist in valstrs for nlist in args.n_sim_seqs_per_gen_list]
    else:
        base_args.append('--n-sim-seqs-per-gen %s' % ':'.join(str(n) for n in args.n_sim_seqs_per_gen_list[0]))
    if len(args.obs_times_list) > 1:
        varnames.append('obs-times')
        valfos = [vlist + [tlist] for vlist in valfos for tlist in args.obs_times_list]
        valstrs = [vlist + [':'.join(str(t) for t in tlist)] for vlist in valstrs for tlist in args.obs_times_list]
    else:
        base_args.append('--obs-times %s' % ':'.join(str(t) for t in args.obs_times_list[0]))
    assert len(valfos) == len(valstrs)

    cmdfos = []
    print '  running %d combinations of: %s' % (len(valfos), ' '.join(varnames))
    for icombo, (vfos, vstrs) in enumerate(zip(valfos, valstrs)):  # NOTE not sure I really need the vfos
        print '   %s' % ' '.join(vstrs)
        outdir = get_bcr_phylo_outdir(varnames, vstrs)
        outfname = '%s/selection/simu/mutated-simu.yaml' % outdir
        if utils.output_exists(args, outfname, offset=8):
            continue
        cmd = './bin/bcr-phylo-run.py --actions simu --base-outdir %s --seed %d %s' % (outdir, args.random_seed, ' '.join(base_args))
        for vname, vstr in zip(varnames, vstrs):
            cmd += ' --%s %s' % (vname, vstr)
        # cmd += ' --debug 1'
        if args.overwrite:
            cmd += ' --overwrite'
        cmdfos += [{
            'cmd_str' : cmd,
            'outfname' : outfname,
            'logdir' : outdir,
            'workdir' : '%s/bcr-phylo-work/%d' % (args.workdir, icombo),
        }]
        print '     %s %s' % (utils.color('red', 'run'), cmd)
    utils.run_cmds(cmdfos, debug='write')

# ----------------------------------------------------------------------------------------
def run_partis(args):
    assert False
    # cmdfos = []
    # print '  running %d lb tau values' % len(args.lb_tau_list)
    # for ilbt, lbt in enumerate(args.lb_tau_list):
    #     print '   %.4f' % lbt
    #     outdir = '%s/partis/bcr-phylo/%s/lb-tau-%.4f' % (os.getenv('fs', default=os.getenv('HOME')), args.label, lbt)
    #     outfname = '%s/selection/simu/mutated-simu.yaml' % outdir
    #     if utils.output_exists(args, outfname, offset=8):
    #         continue
    #     cmd = './bin/bcr-phylo-run.py --n-sim-seqs-per-generation 150 --obs-times 150'
    #     cmd += ' --actions simu --lb-tau %f' % lbt
    #     cmd += ' --seed %d' % args.random_seed
    #     cmd += ' --base-outdir %s' % outdir
    #     # cmd += ' --debug 1'
    #     if args.overwrite:
    #         cmd += ' --overwrite'
    #     cmdfos += [{
    #         'cmd_str' : cmd,
    #         'outfname' : outfname,
    #         'logdir' : outdir,
    #         'workdir' : '%s/bcr-phylo-work/%d' % (args.workdir, ilbt),
    #     }]
    #     print '     %s %s' % (utils.color('red', 'run'), cmd)
    # utils.run_cmds(cmdfos, debug='write')

# ----------------------------------------------------------------------------------------
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('action', choices=['get-max-lbi', 'run-bcr-phylo'])
parser.add_argument('--carry-cap-list', default='250:1000:4000')
parser.add_argument('--n-sim-seqs-per-gen-list', default='50,75,80:200,250')
parser.add_argument('--obs-times-list', default='30,40,50:125,150')
parser.add_argument('--lb-tau-list', default='0.0005:0.001:0.002:0.003:0.005:0.008')
parser.add_argument('--n-tau-lengths-list', help='set either this or --n-generations-list')
parser.add_argument('--n-generations-list', default='4:5:6:7:8:9:10', help='set either this or --n-tau-lengths-list')
parser.add_argument('--seq-len', default=400, type=int)
parser.add_argument('--random-seed', default=2, type=int)  # 1 gives a tree that terminates after two generations
parser.add_argument('--base-outdir', default='%s/partis' % os.getenv('fs', default=os.getenv('HOME')))
parser.add_argument('--label', default='test')
parser.add_argument('--make-plots', action='store_true')
parser.add_argument('--overwrite', action='store_true')  # not really propagated to everything I think
parser.add_argument('--workdir')  # default set below
parser.add_argument('--partis-dir', default=os.getcwd(), help='path to main partis install dir')
parser.add_argument('--ete-path', default=('/home/%s/anaconda_ete/bin' % os.getenv('USER')) if os.getenv('USER') is not None else None)
args = parser.parse_args()

sys.path.insert(1, args.partis_dir + '/python')
try:
    import utils
    import treeutils
    import plotting
except ImportError as e:
    print e
    raise Exception('couldn\'t import from main partis dir \'%s\' (set with --partis-dir)' % args.partis_dir)

args.carry_cap_list = utils.get_arg_list(args.carry_cap_list, intify=True)
args.n_sim_seqs_per_gen_list = utils.get_arg_list(args.n_sim_seqs_per_gen_list, list_of_lists=True, intify=True)
args.obs_times_list = utils.get_arg_list(args.obs_times_list, list_of_lists=True, intify=True)
args.lb_tau_list = utils.get_arg_list(args.lb_tau_list, floatify=True)
args.n_tau_lengths_list = utils.get_arg_list(args.n_tau_lengths_list, floatify=True)
args.n_generations_list = utils.get_arg_list(args.n_generations_list, intify=True)
if [args.n_tau_lengths_list, args.n_generations_list].count(None) != 1:
    raise Exception('have to set exactly one of --n-tau-lengths, --n-generations')

if args.workdir is None:
    args.workdir = utils.choose_random_subdir('/tmp/%s/hmms' % (os.getenv('USER', default='partis-work')))

# ----------------------------------------------------------------------------------------
if args.action == 'get-max-lbi':
    calc_max_lbi(args)
elif args.action == 'run-bcr-phylo':
    run_bcr_phylo(args)
