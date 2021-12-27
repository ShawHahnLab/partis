#!/usr/bin/env python
import sys
import csv
csv.field_size_limit(sys.maxsize)  # make sure we can write very large csv fields
import os
import argparse
import colored_traceback.always

# if you move this script, you'll need to change this method of getting the imports
partis_dir = os.path.dirname(os.path.realpath(__file__)).replace('/bin', '')
sys.path.insert(1, partis_dir + '/python')

import utils
import glutils

# ----------------------------------------------------------------------------------------
def count_plot(tglfo, tlist, plotdir, paired_loci=None):
    if len(tlist) == 0:
        return
    if args.only_count_correlations:
        from corrcounter import CorrCounter
        ccounter = CorrCounter(paired_loci=paired_loci)
        for line in tlist:
            l_info = None
            if paired_loci is not None:
                line, l_info = line
            ccounter.increment(line, l_info=l_info)
        ccounter.plot(plotdir + '/correlations', only_csv=args.only_csv_plots, debug=args.debug)
        return
    if args.simfname is not None:
        simglfo, true_antn_list, _ = utils.read_output(args.simfname)
        true_antn_dict = {}
        for true_line in true_antn_list:
            for iseq, uid in enumerate(true_line['unique_ids']):
                true_antn_dict[uid] = utils.synthesize_single_seq_line(true_line, iseq)
        # true_antn_dict = utils.get_annotation_dict(true_antn_list)
        from performanceplotter import PerformancePlotter
        perfplotter = PerformancePlotter('hmm')
        n_failed = 0
        for line in tlist:
            if line['invalid']:
                n_failed += 1
                continue
            for iseq, uid in enumerate(line['unique_ids']):  # NOTE this counts rearrangement-level parameters once for every mature sequence, which is inconsistent with the pcounters... but I think might make more sense here?
                _ = perfplotter.evaluate(true_antn_dict[uid], utils.synthesize_single_seq_line(line, iseq), simglfo=simglfo)
        perfplotter.plot(args.plotdir, only_csv=args.only_csv_plots)
        if n_failed > 0:
            print '  %s %d / %d failed queries' % (utils.color('yellow', 'warning'), n_failed, len([u for l in tlist for u in l['unique_ids']]))
        if args.only_plot_performance:
            return
    assert not args.paired  # only handled for correlation counting atm
    from parametercounter import ParameterCounter
    setattr(args, 'region_end_exclusions', {r : [0 for e in ['5p', '3p']] for r in utils.regions})  # hackity hackity hackity
    pcounter = ParameterCounter(tglfo, args)  # NOTE doesn't count correlations by default
    for line in tlist:
        pcounter.increment(line)
    pcounter.plot(plotdir, only_csv=args.only_csv_plots) #, make_per_base_plots=True) #, only_overall=True, make_per_base_plots=True

# ----------------------------------------------------------------------------------------
helpstr = """
Extract sequences from a partis output file and write them to a fasta, csv, or tsv file, optionally with a limited amount of extra information for each sequence.
For details of partis output files, see the manual.
To view the partitions and annotations in a partis output file, use the partis \'view-output\' action.
Example usage:
    ./bin/parse-output.py test/reference-results/partition-new-simu.yaml out.fa
"""
class MultiplyInheritedFormatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass
formatter_class = MultiplyInheritedFormatter
parser = argparse.ArgumentParser(formatter_class=MultiplyInheritedFormatter, description=helpstr)
parser.add_argument('infile', help='partis output file from which to read input')
parser.add_argument('outfile', help='file to which to write output extracted from <infile> (fasta or csv/tsv)')
parser.add_argument('--paired', action='store_true', help='if set, <infile> should be a paired output dir, rather than a single file')
parser.add_argument('--extra-columns', help='colon-separated list of additional partis output columns (beyond sequences), to write to the output file. If writing to a fasta file, the column values are appended after the sequence name, separated by --fasta-info-separator. If writing to csv/tsv, they\'re written as proper, labeled columns.')
parser.add_argument('--partition-index', type=int, help='if set, use the partition at this index in the cluster path, rather than the default of using the best partition')
parser.add_argument('--seed-unique-id', help='if set, take sequences only from the cluster containing this seed sequence, rather than the default of taking all sequences from all clusters')
parser.add_argument('--cluster-index', type=int, help='if set, take sequences only from the cluster at this index in the partition, rather than the default of taking all sequences from all clusters. This index is with respect to the cluster order found in the file (which, in contrast to plots made by --plotdir, is *not* sorted by size)')
parser.add_argument('--indel-reversed-seqs', action='store_true', help='if set, take sequences that have had any shm indels "reversed" (i.e. insertions are reversed, and deletions are replaced with the germline bases) rather than the default of using sequences from the original input file. Indel-reversed sequences can be convenient because they are by definition the same length as and aligned to the naive sequence.')
parser.add_argument('--glfo-dir', help='Directory with germline info. Only necessary for old-style csv output files. Equivalent to a parameter dir with \'/hmm/germline-sets\' appended.')
parser.add_argument('--template-glfo-dir', help='use this glfo dir as a template when reading --glfo-dir (only used for airr input atm)')
parser.add_argument('--locus', default='igh', help='only used for old-style csv output files')
parser.add_argument('--plotdir', help='if set, plot annotation parameters from infile to --plotdir and exit (you still have to set outfile, sorry, since it\'s nice having it be a positional arg, but it doesn\'t get used for this). To add e.g. per-gene-per-position plots comment/uncomment args in the call below.')
parser.add_argument('--only-count-correlations', action='store_true', help='instead of counting/plotting all parameters, including correlations, only count and plot correlations (no effect if --plotdir isn\'t set)')
parser.add_argument('--only-plot-performance', action='store_true', help='instead of counting/plotting all parameters, including correlations, only count and plot correlations (no effect if --plotdir isn\'t set)')
parser.add_argument('--fasta-info-separator', default=' ', help='character to use ')
parser.add_argument('--debug', type=int, default=0)
parser.add_argument('--airr-input', action='store_true', help='read input in AIRR tsv format, and if output file suffix is .yaml write partis output.')
parser.add_argument('--airr-output', action='store_true', help='write output in AIRR tsv format')
parser.add_argument('--skip-columns', help='don\'t write these columns to output (atm only implemented for airr output, since we need to remove the clone_id column so scoper doesn\'t crash)')
parser.add_argument('--simfname', help='simulation file corresponding to input file (i.e. presumably <infile> is inference that was performed on --simfname')
parser.add_argument('--only-csv-plots', action='store_true', help='only write csv versions of plots (not svg), which is a lot faster')
parser.add_argument('--only-make-plots', action='store_true', help='if --plotdir is set, set this to only do plotting, i.e. don\'t do the usual/default file reading/conversion')

if 'extract-fasta.py' in sys.argv[0]:  # if they're trying to run this old script, which is now just a link to this one, print a warning and rejigger the arguments so it still works
    print '  note: running deprecated script %s, which currently is just a link pointing to %s' % (os.path.basename(sys.argv[0]), os.path.basename(os.path.realpath( __file__)))
    print '  note: transferring deprecated arguments --input-file and --fasta-output-file to the first two positional arguments (this will continue to work, you only need to change things if you want this warning to go away)'
    utils.insert_in_arglist(sys.argv, [utils.get_val_from_arglist(sys.argv, '--input-file'), utils.get_val_from_arglist(sys.argv, '--fasta-output-file')], sys.argv[0])
    utils.remove_from_arglist(sys.argv, '--input-file', has_arg=True)
    utils.remove_from_arglist(sys.argv, '--fasta-output-file', has_arg=True)

args = parser.parse_args()
args.extra_columns = utils.get_arg_list(args.extra_columns)
assert utils.getsuffix(args.outfile) in ['.csv', '.tsv', '.fa', '.fasta'] or args.airr_input and utils.getsuffix(args.outfile) == '.yaml'

default_glfo_dir = partis_dir + '/data/germlines/human'
if utils.getsuffix(args.infile) in ['.csv', '.tsv'] and args.glfo_dir is None:
    print '  note: reading csv/tsv format without germline info, so need to get germline info from a separate directory; --glfo-dir was not set, so using default %s. If it doesn\'t crash, it\'s probably ok.' % default_glfo_dir
    args.glfo_dir = default_glfo_dir

# ----------------------------------------------------------------------------------------
# read input
if args.paired:
    import paircluster
    def getofn(ltmp, lpair=None):
        ofn = paircluster.paired_fn(args.infile, ltmp, lpair=lpair, suffix='.yaml')
        if not os.path.exists(ofn):  # first look for simy file (just e.g. igh.yaml), if it's not there look for the partition output file
            ofn = paircluster.paired_fn(args.infile, ltmp, lpair=lpair, actstr='partition', suffix='.yaml')
        return ofn
    lp_infos = paircluster.read_lpair_output_files(utils.locus_pairs['ig'], getofn)
else:
    if args.airr_input:
        glfo, glfd = None, args.glfo_dir
        if args.template_glfo_dir is not None:  # NOTE only handled for airr input at the moment, cause that's what i need it for right now
            glfo = glutils.read_glfo(args.glfo_dir, args.locus, template_glfo=glutils.read_glfo(args.template_glfo_dir, args.locus))
            # glutils.write_glfo(args.glfo_dir + '-parsed', glfo, debug=True)
            glfd = None
        glfo, annotation_list, cpath = utils.read_airr_output(args.infile, locus=args.locus, glfo=glfo, glfo_dir=glfd)
    else:
        glfo, annotation_list, cpath = utils.read_output(args.infile, glfo_dir=args.glfo_dir, locus=args.locus)

# plot
if args.plotdir is not None:
    if args.paired:
        for lpair in utils.locus_pairs['ig']:
            if lp_infos[tuple(lpair)]['glfos'] is None:
                continue
            for ltmp in lpair:
                count_plot(lp_infos[tuple(lpair)]['glfos'][ltmp], lp_infos[tuple(lpair)]['antn_lists'][ltmp], '%s/%s/%s'%(args.plotdir, '+'.join(lpair), ltmp))
            antn_pairs = paircluster.find_cluster_pairs(lp_infos, lpair) #, debug=True)
            count_plot(None, antn_pairs, '%s/%s'%(args.plotdir, '+'.join(lpair)), paired_loci=[l['loci'][0] for l in antn_pairs[0]])
    else:
        count_plot(glfo, annotation_list, args.plotdir)
    if args.only_make_plots:
        sys.exit(0)

assert not args.paired  # only handled for plotting above atm

# restrict to certain partitions/clusters
if cpath is None or cpath.i_best is None:
    clusters_to_use = [l['unique_ids'] for l in annotation_list]
    print '  no cluster path in input file, so just using all %d sequences (in %d clusters) in annotations' % (sum(len(c) for c in clusters_to_use), len(clusters_to_use))
else:
    ipartition = cpath.i_best if args.partition_index is None else args.partition_index
    print '  found %d clusters in %s' % (len(cpath.partitions[ipartition]), 'best partition' if args.partition_index is None else 'partition at index %d (of %d)' % (ipartition, len(cpath.partitions)))
    if args.cluster_index is None:
        clusters_to_use = cpath.partitions[ipartition]
        print '    taking all %d clusters' % len(clusters_to_use)
    else:
        clusters_to_use = [cpath.partitions[ipartition][args.cluster_index]]
        print '    taking cluster at index %d with size %d' % (args.cluster_index, len(clusters_to_use[0]))
    if args.seed_unique_id is not None:
        clusters_to_use = [c for c in clusters_to_use if args.seed_unique_id in c]  # NOTE can result in more than one cluster with the seed sequence (e.g. if this file contains intermediate annotations from seed partitioning))
        print '    removing clusters not containing sequence \'%s\' (leaving %d)' % (args.seed_unique_id, len(clusters_to_use))

if not os.path.exists(os.path.dirname(os.path.abspath(args.outfile))):
    os.makedirs(os.path.dirname(os.path.abspath(args.outfile)))

if args.airr_output:
    print '  writing %d sequences to %s' % (len(annotation_list), args.outfile)
    utils.write_airr_output(args.outfile, annotation_list, cpath=cpath, extra_columns=args.extra_columns, skip_columns=args.skip_columns)
    sys.exit(0)

# condense partis info into <seqfos> for fasta/csv output
seqfos = []
annotations = {':'.join(adict['unique_ids']) : adict for adict in annotation_list}  # collect the annotations in a dictionary so they're easier to access
for cluster in clusters_to_use:
    if ':'.join(cluster) not in annotations:
        print '  %s cluster with size %d not in annotations, so skipping it' % (utils.color('red', 'warning'), len(cluster))
        continue
    cluster_annotation = annotations[':'.join(cluster)]
    newfos = [{'name' : u, 'seq' : s} for u, s in zip(cluster_annotation['unique_ids'], cluster_annotation['seqs' if args.indel_reversed_seqs else 'input_seqs'])]
    if args.extra_columns is not None:
        for ecol in args.extra_columns:
            if ecol not in cluster_annotation:
                utils.add_extra_column(ecol, cluster_annotation, cluster_annotation)
                # raise Exception('column \'%s\' not found in annotations' % ecol)
            for iseq in range(len(newfos)):
                ival = cluster_annotation[ecol]
                if ecol in utils.linekeys['per_seq']:
                    ival = ival[iseq]
                newfos[iseq][ecol] = ival
    seqfos += newfos

# write output
print '  writing %d sequences to %s' % (len(seqfos), args.outfile)
with open(args.outfile, 'w') as ofile:
    if utils.getsuffix(args.outfile) in ['.csv', '.tsv']:
        writer = csv.DictWriter(ofile, seqfos[0].keys(), delimiter=',' if utils.getsuffix(args.outfile)=='.csv' else '\t')
        writer.writeheader()
        for sfo in seqfos:
            writer.writerow(sfo)
    elif utils.getsuffix(args.outfile) in ['.fa', '.fasta']:
        for sfo in seqfos:
            estr = ''
            if args.extra_columns is not None:
                estr = args.fasta_info_separator
                estr += args.fasta_info_separator.join(str(sfo[c]) for c in args.extra_columns)
            ofile.write('>%s%s\n%s\n' % (sfo['name'], estr, sfo['seq']))
    elif utils.getsuffix(args.outfile) == '.yaml':
        true_partition = None
        if args.simfname is not None:
            _, _, true_cpath = utils.read_output(args.simfname, skip_annotations=True)
            true_partition = true_cpath.best()
        plines = cpath.get_partition_lines(true_partition=true_partition, calc_missing_values='none' if true_partition is None else 'best')
        utils.write_annotations(args.outfile, glfo, annotation_list, utils.add_lists(utils.annotation_headers, args.extra_columns), partition_lines=plines)
    else:
        assert False
