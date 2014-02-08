"""Filtering of genomic variants.
"""
from distutils.version import LooseVersion
import os

from bcbio import utils
from bcbio.distributed.transaction import file_transaction
from bcbio.pipeline import config_utils
from bcbio.provenance import do, programs
from bcbio.variation import vcfutils

# ## General functionality

def hard_w_expression(vcf_file, expression, data, filterext=""):
    """Perform hard filtering using bcftools expressions like %QUAL < 20 || DP < 4.
    """
    base, ext = utils.splitext_plus(vcf_file)
    out_file = "{base}-filter{filterext}{ext}".format(**locals())
    if not utils.file_exists(out_file):
        with file_transaction(out_file) as tx_out_file:
            bcftools = config_utils.get_program("bcftools", data["config"])
            bedtools = config_utils.get_program("bedtools", data["config"])
            output_type = "z" if out_file.endswith(".gz") else "v"
            variant_regions = data["config"]["algorithm"].get("variant_regions", None)
            if variant_regions:
                intervals = "-t <(sort -k1,1 -k2,2n {variant_regions} | {bedtools} merge -i )".format(**locals())
            else:
                intervals = ""
            cmd = ("{bcftools} filter -o {output_type} {intervals} --soft-filter '+' "
                   "-e '{expression}' -m '+' {vcf_file} > {tx_out_file}")
            do.run(cmd.format(**locals()), "Hard filtering %s with %s" % (vcf_file, expression), data)
    return out_file

# ## Caller specific

def freebayes(in_file, ref_file, vrn_files, data):
    """FreeBayes filters: trying custom filter approach before falling back on hard filtering.
    """
    out_file = _freebayes_hard(in_file, data)
    #out_file = _freebayes_custom(in_file, ref_file, data)
    return out_file

def _freebayes_custom(in_file, ref_file, data):
    """Custom FreeBayes filtering using bcbio.variation, tuned to human NA12878 results.
    """
    if vcfutils.get_paired_phenotype(data):
        return None
    config = data["config"]
    bv_ver = programs.get_version("bcbio_variation", config=config)
    if LooseVersion(bv_ver) < LooseVersion("0.1.1"):
        return None
    out_file = "%s-filter%s" % os.path.splitext(in_file)
    if not utils.file_exists(out_file):
        tmp_dir = utils.safe_makedir(os.path.join(os.path.dirname(in_file), "tmp"))
        bv_jar = config_utils.get_jar("bcbio.variation",
                                      config_utils.get_program("bcbio_variation", config, "dir"))
        resources = config_utils.get_resources("bcbio_variation", config)
        jvm_opts = resources.get("jvm_opts", ["-Xms750m", "-Xmx2g"])
        java_args = ["-Djava.io.tmpdir=%s" % tmp_dir]
        cmd = ["java"] + jvm_opts + java_args + ["-jar", bv_jar, "variant-filter", "freebayes",
                                                 in_file, ref_file]
        do.run(cmd, "Custom FreeBayes filtering using bcbio.variation")
    return out_file

def _freebayes_hard(in_file, data):
    """Perform basic sanity filtering of FreeBayes results, removing low confidence calls.
    """
    filters = "%QUAL < 200 || DP < 5"
    return hard_w_expression(in_file, filters, data)
