"""===========================
pipeline_chiptools
===========================

.. Replace the documentation below with your own description of the
   pipeline's purpose

Overview
========

This pipeline computes the word frequencies in the configuration
files :file:``pipeline.ini` and :file:`conf.py`.

Usage
=====

See :ref:`PipelineSettingUp` and :ref:`PipelineRunning` on general
information how to use CGAT pipelines.

Configuration
-------------

The pipeline requires a configured :file:`pipeline.ini` file.
CGATReport report requires a :file:`conf.py` and optionally a
:file:`cgatreport.ini` file (see :ref:`PipelineReporting`).

Default configuration files can be generated by executing:

   python <srcdir>/pipeline_@template@.py config

Input files
-----------

None required except the pipeline configuration files.

Requirements
------------

The pipeline requires the results from
:doc:`pipeline_annotations`. Set the configuration variable
:py:data:`annotations_database` and :py:data:`annotations_dir`.

Pipeline output
===============

.. Describe output files of the pipeline here

Glossary
========

.. glossary::



####### need to add that the reuirements are a bed file#####

Code
====

"""
from ruffus import *
import sys
import os
import CGAT.Experiment as E
import CGATPipelines.Pipeline as P
import CGATPipelines.PipelinePeakcalling as PipelinePeakcalling
import CGAT.BamTools as Bamtools
import CGAT.IOTools as IOTools
import matplotlib.pyplot as plt
import pandas as pd

# load options from the config file
PARAMS = P.getParameters(
    ["%s/pipeline.ini" % os.path.splitext(__file__)[0],
     "../pipeline.ini",
     "pipeline.ini"])


#######################################################################
# Check for design file & Match ChIP/ATAC-Seq Bams with Inputs ########
#######################################################################


# This section checks for the design table and generates:
# 1. A dictionary, inputD, linking each input file and each of the various
#    IDR subfiles to the appropriate input, as specified in the design table
# 2. A pandas dataframe, df, containing the information from the
#    design table.
# 3. INPUTBAMS: a list of control (input) bam files to use as background for
#    peakcalling.
# 4. CHIPBAMS: a list of experimental bam files on which to call peaks on.

# if design table is missing the input and chip bams  to empty list. This gets
# round the import tests


if os.path.exists("design.tsv"):
    df, inputD = PipelinePeakcalling.readDesignTable("design.tsv",
                                                 PARAMS["general_poolinputs"])

    INPUTBAMS = list(df['bamControl'].values)
    CHIPBAMS = list(df['bamReads'].values)
    TOTALBAMS = INPUTBAMS + CHIPBAMS

    # I have defined a dict of the samples to I can parse the correct
    # inputs into bamCompare
    SAMPLE_DICT = {}
    for chip, inputs in zip(CHIPBAMS, INPUTBAMS):
        key = chip
        value = inputs
        SAMPLE_DICT[key] = value

else:
    E.warn("design.tsv is not located within the folder")
    INPUTBAMS = []
    CHIPBAMS = []


#########################################################################
# Connect to database
#########################################################################

def connect():
    '''
    Setup a connection to an sqlite database
    '''

    dbh = sqlite3.connect(PARAMS['database'])
    return dbh

###########################################################################
# start of pipelined tasks
# 1) Preprocessing Steps - Filter bam files & generate bam stats
###########################################################################


@transform("design.tsv", suffix(".tsv"), ".load")
def loadDesignTable(infile, outfile):
    ''' load design.tsv to database '''
    P.load(infile, outfile)


#####################################################
# makeTagDirectory Inputs
#####################################################

@active_if(PARAMS['homer'])
@follows(mkdir("homer"))
@follows(loadDesignTable)
@transform(INPUTBAMS, regex("(.*).bam"),
           r"homer.dir/\1/\1.txt")
def makeTagDirectoryInput(infile, outfile):
    '''This will create a tag file for each bam file
    for a CHIP-seq experiment
    '''

    bamstrip = infile.strip(".bam")
    samfile = bamstrip + ".sam"

    statement = '''samtools index %(infile)s;
                   samtools view %(infile)s > %(samfile)s;
                   makeTagDirectory
                   -genome %(homer_maketagdir_genome)s -checkGC
                   %(bamstrip)s/ %(samfile)s
                   &> %(bamstrip)s.makeTagInput.log;
                   touch %(bamstrip)s/%(bamstrip)s.txt'''

    P.run()


#####################################################
# makeTagDirectory ChIPs
#####################################################


@active_if(PARAMS['homer'])
@follows(loadDesignTable)
@transform(CHIPBAMS, regex("(.*).bam"),
           r"homer/\1/\1.txt")
def makeTagDirectoryChips(infile, outfile):
    '''This will create a tag file for each bam file
    for a CHIP-seq experiment
    '''

    bamstrip = infile.strip(".bam")
    samfile = bamstrip + ".sam"

    statement = '''samtools index %(infile)s;
                   samtools view %(infile)s > %(samfile)s;
                   makeTagDirectory
                   %(bamstrip)s/ %(samfile)s
                   -genome %(homer_maketagdir_genome)s -checkGC
                   &> %(bamstrip)s.makeTagChip.log;
                   touch %(bamstrip)s/%(bamstrip)s.txt'''

    P.run()

@active_if(PARAMS['homer'])
@transform((makeTagDirectoryChips),
           regex("(.*)/(.*).txt"),
           r"\1/regions.txt")
def findPeaks(infile, outfile):

    '''

    Arguments
    ---------
    infiles : string
         this is a list of tag directories
    directory: string
         This is the directory where the tag file will be placed'''

    directory = infile.strip(".txt")
    directory, _ = directory.split("/")
    bamfile = directory + ".bam"

    df_slice = df[df['bamReads'] == bamfile]
    input_bam = df_slice['bamControl'].values[0]
    input_bam = input_bam.strip(".bam")

    statement = '''findPeaks %(directory)s -style %(homer_findpeaks_style)s -o %(homer_findpeaks_output)s
                   %(homer_findpeaks_options)s -i %(input_bam)s &> %(directory)s.findpeaks.log'''
    P.run()


@active_if(PARAMS['homer'])
@transform(findPeaks,
           regex("(.*)/regions.txt"),
           r"\1/\1.bed")
def bedConversion(infile, outfile):

    ''' '''

    statement = '''pos2bed.pl %(homer_BED_options)s %(infile)s > %(outfile)s'''

    P.run()


@active_if(PARAMS['homer'])
@transform(findPeaks,
           regex("(.*)/regions.txt"),
           r"\1/annotate.txt")
def annotatePeaks(infile, outfile):

    ''' '''

    statement = '''annotatePeaks.pl %(infile)s %(homer_annotatePeaks_genome)s &> Annotate.log > %(outfile)s'''

    P.run()


@active_if(PARAMS['homer'])
@transform(findPeaks,
           regex("(.*)/regions.txt"),
           r"\1/motifs.txt")
def findMotifs(infile, outfile):

    directory, _ = infile.split("/")

    statement = '''findMotifsGenome.pl %(infile)s %(homer_motif_genome)s %(directory)s -size %(homer_motif_size)i
                   &> Motif.log'''

    P.run()


@active_if(PARAMS['homer'])
@active_if(PARAMS['diffannotat_raw'])
@merge(makeTagDirectoryChips, "countTable.peaks.txt")
def annotatePeaksRaw(infiles, outfile):

    directories = []

    for infile in infiles:
        directory = infile.split("/")[0]
        directories.append(directory + "/")

    directories = " ".join(directories)

    statement = '''annotatePeaks.pl %(homer_annotate_raw_region)s %(homer_annotate_raw_genome)s
                   -d %(directories)s > countTable.peaks.txt'''

    P.run()


@active_if(PARAMS['homer'])
@active_if(PARAMS['diffexpr'])
@transform(annotatePeaksRaw,
           suffix(".peaks.txt"),
           ".diffexprs.txt")
def getDiffExprs(infile, outfile):

    statement = '''getDiffExpression.pl %(infile)s
                  %(homer_diff_expr_options)s %(homer_diff_expr_group)s > diffOutput.txt'''

    P.run()


 # ruffus decorator is wrong but it need changing later

@active_if(PARAMS['homer'])
@active_if(PARAMS['diff_repeats'])
@follows(mkdir("homer/Replicates.dir"))
@follows(makeTagDirectoryChips)
@originate("homer/Replicates.dir/outputPeaks.txt")
def getDiffPeaksReplicates(outfile):

    replicates = set(df["Replicate"])

    for x in replicates:
        subdf = df[df["Replicate"] == x]

        bams = subdf["bamReads"].values

        bam_strip = []
        for bam in bams:
            bam = bam.strip(".bam") + "/"
            bam_strip.append(bam)

    bam_strip = " ".join(bam_strip)

    inputs = subdf["bamControl"].values

    input_strip = []
    for inp in inputs:
        inp = inp.strip(".bam") + "/"
        input_strip.append(inp)

    input_strip = " ".join(input_strip)

    statement = '''getDifferentialPeaksReplicates.pl -t %(bam_strip)s
                       -i %(input_strip)s -genome %(homer_diff_repeats_genome)s %(homer_diff_repeats_options)s>
                       homer/Replicates.dir/Repeat-%(x)s.outputPeaks.txt'''

    P.run()


##################################################################################################
## This is the section where the deeptool (http://deeptools.readthedocs.io/en/latest/index.html#)
#  deepTools is a suite of python tools particularly developed for the efficient analysis 
#  of high-throughput sequencing data, such as ChIP-seq, RNA-seq or MNase-seq
## Functions are specified
##################################################################################################


@active_if(PARAMS['deeptools'])
@follows(mkdir("deepTools/Plot.dir/Coverage.dir"))
@follows(loadDesignTable)
@merge([CHIPBAMS,INPUTBAMS], "deepTools/Plot.dir/Coverage.dir/coverage_plot.eps")
def coverage_plot(infiles, outfile):

    infile = [item for sublist in infiles for item in sublist]
    infile = " ".join(infile)

    if PARAMS['deep_ignore_dups'] == True:
        duplicates = "--ignoreDuplicates"
    elif PARAMS['deep_ignore_dups'] == False:
        duplicates = ""
    else:
        raise ValueError('''Please set a ignore_dups value in the
                   pipeline.ini''')

    statement = '''plotCoverage -b %(infile)s
                   --plotFile %(outfile)s
                   --plotTitle "coverage_plot"
                   --outRawCounts deepTools/Plot.dir/Coverage.dir/coverage_plot.tab
                   %(duplicates)s
                   --minMappingQuality %(deep_mapping_qual)s'''

    P.run()


@active_if(PARAMS['deeptools'])
@follows(mkdir("deepTools/Plot.dir/Fingerprint.dir"))
@follows(loadDesignTable)
@merge([CHIPBAMS,INPUTBAMS], "deepTools/Plot.dir/Fingerprint.dir/fingerprints.eps")
def fingerprint_plot(infiles, outfile):

    infile = [item for sublist in infiles for item in sublist]
    infile = " ".join(infile)

    if PARAMS['deep_ignore_dups'] == True:
        duplicates = "--ignoreDuplicates"
    elif PARAMS['deep_ignore_dups'] == False:
        duplicates = ""
    else:
        raise ValueError('''Please set a ignore_dups value in the
                   pipeline.ini''')

    statement = '''plotFingerprint -b %(infile)s
                   --plotFile %(outfile)s
                   --plotTitle "Fingerprints of samples"
                   --outRawCounts deepTools/Plot.dir/Fingerprint.dir/fingerprints_plot.tab
                   %(duplicates)s
                   --minMappingQuality %(deep_mapping_qual)s'''

    P.run()

@active_if(PARAMS['deeptools'])
@follows(mkdir("deepTools/Plot.dir/FragmentSize.dir"))
@follows(loadDesignTable)
@merge([CHIPBAMS,INPUTBAMS], "deepTools/Plot.dir/FragmentSize.dir/FragmentSize.png")
def fragment_size(infiles, outfile):

    infile = [item for sublist in infiles for item in sublist]
    infile = " ".join(infile)

    if PARAMS['deep_logscale'] is not "":
        logscale = ("--logScale %s") % (PARAMS['deep_logscale'])
    else:
        logscale = ""
    
    statement = '''bamPEFragmentSize -b %(infile)s
                   --histogram %(outfile)s
                   %(logscale)s'''

    P.run()


@active_if(PARAMS['deeptools'])
@active_if(PARAMS['deep_bam_coverage'])
@follows(mkdir("deepTools/Bwfiles.dir/bamCoverage.dir"))
@transform(TOTALBAMS, regex("(.*).bam"),
           r"deepTools/Bwfiles.dir/bamCoverage.dir/\1.bw")
def bamCoverage(infiles, outfile):

    if PARAMS['deep_ignore_norm'] is not "":
        normalise  = '--ignoreForNormalization '
        norm_value = PARAMS['deep_ignore_norm']

    else:
        normalise  = ''
        norm_value = ''


    if PARAMS['deep_extendreads'] == True:
        extend = '--extendReads'
    elif PARAMS['deep_extendreads'] == False:
        extend = ''
    else:
        raise ValueError('''Please set the extendreads to a value 0 or 1''')

    statement = '''bamCoverage --bam %(infiles)s
                   -o %(outfile)s
                   -of bigwig
                   --binSize %(deep_binsize)s
                   %(normalise)s %(norm_value)s
                   %(extend)s
                   %(deep_bamcoverage_options)s'''

    P.run()

@active_if(PARAMS['deeptools'])
@active_if(PARAMS['deep_bam_compare'])
@follows(loadDesignTable)
@follows(mkdir("deepTools/Bwfiles.dir/bamCompare.dir"))
@transform(CHIPBAMS,
           suffix('.bam'),
           add_inputs(SAMPLE_DICT),
           r"deepTools/Bwfiles.dir/bamCompare.dir/\1.bw")
def bamCompare(infiles, outfile):

    chipbam = infiles[0]
    inputbams = infiles[1]
    inputbam = inputbams[chipbam]

    statement = '''bamCompare -b1 %(chipbam)s
                       -b2 %(inputbam)s
                       -o %(outfile)s
                       -of bigwig
                       %(deep_bamcompare_options)s'''

    P.run()


@active_if(PARAMS['deeptools'])
@follows(loadDesignTable)
@follows(mkdir("deepTools/Summary.dir"))
@merge([CHIPBAMS,INPUTBAMS], "deepTools/Summary.dir/Bam_Summary.npz")
def multiBamSummary(infiles, outfile):

    infile = [item for sublist in infiles for item in sublist]
    infile = " ".join(infile)

    if PARAMS['deep_mode_setting'] == 'None':
        mode_set = 'bins'
        mode_region = ''
    else:
        mode_set  = 'BED-file --BED '
        mode_region = PARAMS['deep_mode_setting']

    if PARAMS['deep_ignore_dups'] == True:
        duplicates = "--ignoreDuplicates"
    elif PARAMS['deep_ignore_dups'] == False:
        duplicates = ""
    else:
        raise ValueError('''Please set a ignore_dups value in the
                   pipeline.ini''')

    statement = '''multiBamSummary %(mode_set)s %(mode_region)s
                   -b %(infile)s
                   -o %(outfile)s
                   --outRawCounts deepTools/Summary.dir/Bam_Summary.tab
                   --minMappingQuality %(deep_mapping_qual)s
                   %(deep_summary_options)s'''

    P.run()

@active_if(PARAMS['deeptools'])
@merge([bamCoverage,bamCompare], "deepTools/Summary.dir/bw_summary.npz")
def multiBwSummary(infiles, outfile):
     
    infiles = " ".join(infiles)

    if PARAMS['deep_mode_setting'] == 'None':
        mode_set = 'bins'
        mode_region = ''
    else:
        mode_set  = 'BED-file --BED '
        mode_region = PARAMS['deep_mode_setting']


    statement = '''multiBigwigSummary %(mode_set)s %(mode_region)s
                   -b %(infiles)s
                   -out %(outfile)s
                   --outRawCounts deepTools/Summary.dir/Bw_Summary.tab
                   %(deep_summary_options)s'''

    P.run()

@active_if(PARAMS['deeptools'])
@follows(mkdir("deepTools/Plot.dir/Summary.dir/"))
@transform((multiBamSummary, multiBwSummary),
            suffix(".npz"),
            r"deepTools/Plot.dir/\1corr")

def plotCorrelation(infiles, outfile):
               
    if PARAMS['deep_plot'] == 'heatmap':
        colormap = ("--colorMap %s") % (PARAMS['deep_colormap'])
    else:
        colormap = ""

    statement = '''plotCorrelation -in %(infiles)s -o %(outfile)s
                   --corMethod %(deep_cormethod)s -p %(deep_plot)s
                   %(colormap)s
                   --plotFileFormat %(deep_filetype)s
                   --skipZeros %(deep_plot_options)s'''
    P.run()

@active_if(PARAMS['deeptools'])
@transform((multiBamSummary, multiBwSummary),
            suffix(".npz"),
            r"deepTools/Plot.dir/\1PCA")

def plotPCA(infiles, outfile):
               
    statement = '''plotPCA -in %(infiles)s -o %(outfile)s
                   --plotFileFormat %(deep_filetype)s
                   %(deep_plot_options)s'''
    P.run()


@active_if(PARAMS['deeptools'])
@follows(mkdir("deepTools/Plot.dir/matrix.dir/"))
@merge([bamCoverage,bamCompare],
       "deepTools/Plot.dir/matrix.dir/matrix.gz")

def computeMatrix(infile, outfile):

    infile = " ".join(infile)

    if 'reference-point' in PARAMS['deep_startfactor']:
       reference_point = '--referencePoint'
       regions = PARAMS['deep_regions']
       region_length = " "
    elif "scale-regions" in PARAMS['deep_startfactor']:
       reference_point == '--regionBodyLength'
       regions = " "
       region_length = PARAMS['deep_region_length']
    else:
        raise(ValueError("Please supply a valid startfactor"))

    if ".gz" in PARAMS['deep_bedfile']:
        infile = PARAMS['deep_bedfile']
        bedfile = IOTools.openFile(infile, "r")
    else:
        bedfile = PARAMS['deep_bedfile']

    if PARAMS['deep_brslength'] is not "":
        upstream = ("--upstream %s") % (PARAMS['deep_brslength'])
    
    if PARAMS['deep_arslength'] is not "":
        downstream = ("--downstream %s") % (PARAMS['deep_arslength'])
    
    if PARAMS['deep_matrix_bin_size'] is not "":
        binsize = ("--binSize %s") % (PARAMS['deep_matrix_bin_size'])
    else:
        binsize = ""

    if PARAMS['deep_out_namematrix'] is not "":
        outmatrix = ("--outFileNameMatrix %s") % (PARAMS['deep_out_namematrix'])
    else:
        outmatrix = ""

    if PARAMS['deep_out_sorted'] is not "":
        sortedfile = ("--outFileSortedRegions %s") % (PARAMS['deep_out_sorted'])
    else:
        sortedfile = ""

    statement = '''computeMatrix %(deep_startfactor)s -S %(infile)s 
                   -R %(bedfile)s
                   %(reference_point)s %(regions)s %(region_length)s
                   %(upstream)s
                   %(downstream)s
                   %(binsize)s
                   --skipZeros
                   -o %(outfile)s 
                   %(outmatrix)s
                   %(sortedfile)s '''
    P.run()

@active_if(PARAMS['deeptools'])
@transform(computeMatrix,
           suffix(".gz"),
           r"deepTools/\1_heatmap.eps")

def plotHeatmap(infile, outfile):
    
    infile ="".join(infile)

    statement = '''plotHeatmap -m %(infile)s
                   -o %(outfile)s
                   --outFileNameMatrix %(deep_out_namematrix)s
                   --outFileSortedRegions %(deep_out_sorted)s
                   --dpi %(deep_dpi)s
                   --colorMap %(deep_colormap)s
                   --kmeans %(deep_kmeans)s 
                   --legendLocation %(deep_legendlocation)s
                   --refPointLabel %(deep_refpointlabel)s'''

    P.run()

@active_if(PARAMS['deeptools'])
@transform(computeMatrix,
           suffix(".gz"),
           r"deepTools/\1_profile.eps")

def plotProfile(infile, outfile):

    infile = "".join(infile)

    if PARAMS['deep_pergroup'] is not "":
        pergroup = ("--perGroup %s") % (PARAMS['deep_pergroup'])
    else:
        pergroup = ""

    statement = '''plotProfile -m %(infile)s
                   -o %(outfile)s
                   --kmeans %(deep_kmeans)s
                   --plotType %(deep_plottype)s
                   --dpi %(deep_dpi)s
                   %(pergroup)s
                   --legendLocation %(deep_legendlocation)s
                   --refPointLabel %(deep_refpointlabel)s'''

    P.run()


# ---------------------------------------------------
# Generic pipeline tasks


@follows(loadDesignTable,
         bedConversion,
         annotatePeaks,
         annotatePeaksRaw,
         getDiffExprs,
         getDiffPeaksReplicates,
         findMotifs,
         coverage_plot,
         fingerprint_plot,
         bamCompare,
         bamCoverage,
         multiBamSummary,
         multiBwSummary,
         plotCorrelation,
         plotPCA,
         computeMatrix,
         plotHeatmap,
         plotProfile)

def full():
    pass


@follows(mkdir("Jupyter_report.dir"))
def renderJupyterReport():
    '''build Jupyter notebook report'''

    report_path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                               'pipeline_docs',
                                               'pipeline_homer',
                                               'Jupyter_report'))

    statement = ''' cp %(report_path)s/* Jupyter_report.dir/ ; cd Jupyter_report.dir/;
                    jupyter nbconvert --ExecutePreprocessor.timeout=None --to html --execute *.ipynb;
                 '''

    P.run()


# We will implement this when the new version of multiqc is available
@follows(mkdir("MultiQC_report.dir"))
@originate("MultiQC_report.dir/multiqc_report.html")
def renderMultiqc(infile):
    '''build mulitqc report'''

    statement = '''LANG=en_GB.UTF-8 multiqc . -f;
                   mv multiqc_report.html MultiQC_report.dir/'''

    P.run()


@follows(renderJupyterReport)
def build_report():
    pass


def main(argv=None):
    if argv is None:
        argv = sys.argv
    P.main(argv)


if __name__ == "__main__":
    sys.exit(P.main(sys.argv))
