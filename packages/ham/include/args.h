#ifndef HAM_ARGS_H
#define HAM_ARGS_H
#include <map>
#include <set>
#include <fstream>
#include <cassert>

#include <text.h>
#include "tclap/CmdLine.h"
using namespace TCLAP;
using namespace std;
namespace ham {
// ----------------------------------------------------------------------------------------
// input processing class
// NOTE some input is passed on the command line (global configuration), while some is passed in a csv file (stuff that depends on each (pair of) sequence(s)).
class Args {
public:
  Args(int argc, const char * argv[]);
  // void Check();  // make sure everything's the same length (i.e. the input file had all the expected columns)

  string hmmdir() { return hmmdir_arg_.getValue(); }
  string datadir() { return datadir_arg_.getValue(); }
  string infile() { return infile_arg_.getValue(); }
  string outfile() { return outfile_arg_.getValue(); }
  string cachefile() { return cachefile_arg_.getValue(); }
  float hamming_fraction_bound_lo() { return hamming_fraction_bound_lo_arg_.getValue(); }
  float hamming_fraction_bound_hi() { return hamming_fraction_bound_hi_arg_.getValue(); }
  float max_logprob_drop() { return max_logprob_drop_arg_.getValue(); }
  string algorithm() { return algorithm_arg_.getValue(); }
  string ambig_base() { return ambig_base_arg_.getValue(); }
  int debug() { return debug_arg_.getValue(); }
  int n_best_events() { return n_best_events_arg_.getValue(); }
  int smc_particles() { return smc_particles_arg_.getValue(); }
  int naive_hamming_cluster() { return naive_hamming_cluster_arg_.getValue(); }
  bool chunk_cache() { return chunk_cache_arg_.getValue(); }
  bool partition() { return partition_arg_.getValue(); }
  bool truncate_seqs() { return truncate_seqs_arg_.getValue(); }
  bool rescale_emissions() { return rescale_emissions_arg_.getValue(); }
  bool unphysical_insertions() { return unphysical_insertions_arg_.getValue(); }
  bool cache_naive_seqs() { return cache_naive_seqs_arg_.getValue(); }

  // command line arguments
  vector<string> algo_strings_;
  vector<int> debug_ints_;
  ValuesConstraint<string> algo_vals_;
  ValuesConstraint<int> debug_vals_;
  ValueArg<string> hmmdir_arg_, datadir_arg_, infile_arg_, outfile_arg_, cachefile_arg_, algorithm_arg_, ambig_base_arg_;
  ValueArg<float> hamming_fraction_bound_lo_arg_, hamming_fraction_bound_hi_arg_, max_logprob_drop_arg_;
  ValueArg<int> debug_arg_, n_best_events_arg_, smc_particles_arg_, naive_hamming_cluster_arg_;
  SwitchArg chunk_cache_arg_, partition_arg_, truncate_seqs_arg_, rescale_emissions_arg_, unphysical_insertions_arg_, cache_naive_seqs_arg_;

  // arguments read from csv input file
  map<string, vector<string> > strings_;
  map<string, vector<int> > integers_;
  map<string, vector<double> > floats_;
  map<string, vector<vector<string> > > str_lists_;
  map<string, vector<vector<int> > > int_lists_;
  map<string, vector<vector<double> > > float_lists_;
  set<string> str_headers_, int_headers_, float_headers_, str_list_headers_, int_list_headers_, float_list_headers_;
};
}
#endif
