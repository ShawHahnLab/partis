import csv
import math
from opener import opener
from utils import is_normed

# ----------------------------------------------------------------------------------------
class Hist(object):
    """ a simple histogram """
    def __init__(self, n_bins, xmin, xmax):
        self.n_bins = n_bins
        self.xmin = float(xmin)
        self.xmax = float(xmax)
        self.low_edges = []  # lower edge of each bin
        self.centers = []  # center of each bin
        self.bin_contents = []
        self.sum_weights_squared = []
        dx = (self.xmax - self.xmin) / self.n_bins
        for ib in range(self.n_bins + 2):  # using ROOT conventions: zero is underflow and last bin is overflow
            self.low_edges.append(self.xmin + (ib-1)*dx)  # subtract one from ib so underflow bin has upper edge xmin
            self.centers.append(self.low_edges[-1] + 0.5*dx)
            self.bin_contents.append(0.0)
            self.sum_weights_squared.append(0.0)

    # ----------------------------------------------------------------------------------------
    def fill_bin(self, ibin, weight=1.0):
        self.bin_contents[ibin] += weight
        self.sum_weights_squared[ibin] += weight*weight

    # ----------------------------------------------------------------------------------------
    def fill(self, value, weight=1.0):
        if value < self.low_edges[0]:  # underflow
            self.fill_bin(0, weight)
        elif value >= self.low_edges[self.n_bins + 1]:  # overflow
            self.fill_bin(self.n_bins + 1, weight)
        else:
            for ib in range(self.n_bins + 2):  # loop over the rest of the bins
                if value >= self.low_edges[ib] and value < self.low_edges[ib+1]:
                    self.fill_bin(ib, weight)

    # ----------------------------------------------------------------------------------------
    def normalize(self):
        sum_value = 0.0
        for ib in range(1, self.n_bins + 1):  # don't include under/overflows in sum_value
            sum_value += self.bin_contents[ib]
        if sum_value == 0.0:
            print 'WARNING sum zero in Hist::normalize, returning without doing anything'
            return
        # make sure there's not too much stuff in the under/overflows
        if self.bin_contents[0]/sum_value > 1e-10 or self.bin_contents[self.n_bins+1]/sum_value > 1e-10:
            print 'WARNING under/overflows'
        for ib in range(1, self.n_bins + 1):
            self.bin_contents[ib] /= sum_value
            self.sum_weights_squared[ib] /= sum_value*sum_value
        check_sum = 0.0
        for ib in range(1, self.n_bins + 1):  # check it
            check_sum += self.bin_contents[ib]
        assert is_normed(check_sum, this_eps=1e-10)

    # ----------------------------------------------------------------------------------------
    def write(self, outfname):
        with opener('w')(outfname) as outfile:
            writer = csv.DictWriter(outfile, ('bin_low_edge', 'contents', 'sum-weights-squared'))
            writer.writeheader()
            for ib in range(self.n_bins + 2):
                writer.writerow({'bin_low_edge':self.low_edges[ib], 'contents':self.bin_contents[ib], 'sum-weights-squared':self.sum_weights_squared[ib]})

    # # ----------------------------------------------------------------------------------------
    # def read(fname, hist_label='', log='', normalize=False):
    #     """ 
    #     Return root histogram with each bin low edge and bin content read from <fname> 
    #     E.g. from the results of hist.Hist.write()
    #     """
    #     low_edges, contents, bin_labels, bin_errors, sum_weights_squared = [], [], [], [], []
    #     xtitle = ''
    #     # print '---- %s' % fname
    #     with opener('r')(fname) as infile:
    #         reader = csv.DictReader(infile)
    #         for line in reader:
    #             low_edges.append(float(line['bin_low_edge']))
    #             contents.append(float(line['contents']))
    #             if 'sum-weights-squared' in line:
    #                 # print '  ', line['contents'], line['sum-weights-squared']
    #                 sum_weights_squared.append(float(line['sum-weights-squared']))
    #             if 'binerror' in line:
    #                 # print '  ', line['contents'], line['binerror']
    #                 bin_errors.append(float(line['binerror']))
    #             if 'binlabel' in line:
    #                 bin_labels.append(line['binlabel'])
    #             else:
    #                 bin_labels.append('')
    #             if 'xtitle' in line:
    #                 xtitle = line['xtitle']
    
    #     n_bins = len(low_edges) - 2  # file should have a line for the under- and overflow bins
    #     xbins = array('f', [0.0 for i in range(n_bins+1)])  # NOTE has to be n bins *plus* 1
    #     low_edges = sorted(low_edges)
    #     for ib in range(n_bins+1):
    #         xbins[ib] = low_edges[ib+1]  # low_edges[1] is the lower edge of the first bin, i.e. the first bin after the underflow bin, and this will set the last entry in xbins to lower[n_bins+1], i.e. the lower edge of the overflow bin. Which, I bloody well think, is correct
    #     hist = TH1D(hist_label, '', n_bins, xbins)  # this will barf if the csv file wasn't sorted by bin low edge
    #     hist.GetXaxis().SetTitle(xtitle)
    #     for ib in range(n_bins+2):
    #         hist.SetBinContent(ib, contents[ib])
    #         if len(sum_weights_squared) > 0:
    #             hist.SetBinError(ib, math.sqrt(sum_weights_squared[ib]))
    #         elif len(bin_errors) > 0:
    #             hist.SetBinError(ib, bin_errors[ib])
    #         else:
    #             hist.SetBinError(ib, math.sqrt(contents[ib]))
    #         if bin_labels[ib] != '':
    #             hist.GetXaxis().SetBinLabel(ib, bin_labels[ib])
    
    #     if normalize and hist.Integral() > 0.0:
    #         hist.Scale(1./hist.Integral())
    #         hist.GetYaxis().SetTitle('freq')
    
