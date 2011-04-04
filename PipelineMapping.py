################################################################################
#
#   MRC FGU Computational Genomics Group
#
#   $Id$
#
#   Copyright (C) 2009 Andreas Heger
#
#   This program is free software; you can redistribute it and/or
#   modify it under the terms of the GNU General Public License
#   as published by the Free Software Foundation; either version 2
#   of the License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#################################################################################
'''
PipelineMapping.py - Utility functions for mapping
==================================================

:Author: Andreas Heger
:Release: $Id$
:Date: |today|
:Tags: Python

Mapping reads is a common task in pipelines. Different pipelines
combine different sources of input (:term:`fastq` files, :term:`sra` files)
of different data (single end, paired end) with different mapping
algorithms (bowtie, tophat, stampy). This module provides utility 
functions to abstract some of these variations.

The pipeline does not know what kind of data it gets (a :term:`sra` archive
might contain single end or paired end data or both).

A pipeline might get several input data (:term:`fastq` and :term:`sra`
formatted files at the same time).

The module currently is able to deal with:

   * tophat mapping against genome
   * bowtie mapping against transcriptome

It implements:
   * .sra: paired-end and single-end
   * .fastq: paired-end and single-end
   * .csfasta: colour-space, single-end

Code
----

'''

import os, sys, shutil, glob
import Pipeline as P

class Mapper( object ):
    '''map reads.

    preprocesses the input data, calls mapper and post-process the output data.
    
    All in a single statement to be send to the cluster.
    '''
    
    datatype = "fastq"

    def __init__(self):
        pass

    def preprocess( self, infiles, outfile ):
        '''build preprocessing statement

        returns statement and fastq files to map.

        Mapping qualities are changed to solexa format.
        '''
        tmpdir_fastq = P.getTempDir()

        # create temporary directory again for nodes
        statement = [ "mkdir -p %s" % tmpdir_fastq ]
        fastqfiles = []
        for infile in infiles:

            if infile.endswith( ".sra"):
                track = P.snip( infile, ".sra" )

                # sneak preview to determine if paired end or single end
                outdir = P.getTempDir()
                P.execute( "fastq-dump -X 1000 --outdir %(outdir)s %(infile)s" % locals() )
                f = glob.glob( os.path.join( outdir, "*.fastq" ) )
                if len(f) == 3:
                    f = glob.glob( os.path.join( outdir, "*_[12].fastq" ) )
                shutil.rmtree( outdir )
                fastqfiles.append( [ "%s/%s" % (tmpdir_fastq, os.path.basename( x )) for x in sorted(f) ] )
                statement.append( "fastq-dump --outdir %(tmpdir_fastq)s %(infile)s" % locals() )
                
            elif infile.endswith( ".fastq.gz" ):
                track = P.snip( os.path.basename( infile ), ".fastq.gz" )
                statement.append(  """gunzip < %(infile)s 
                                      | python %%(scriptsdir)s/fastq2fastq.py --change-format=sanger --guess-format=phred64 --log=%(outfile)s.log
                                      > %(tmpdir_fastq)s/%(track)s.fastq""" % locals() )
                fastqfiles.append( ("%s/%s.fastq" % (tmpdir_fastq, track),) )

            elif infile.endswith( ".csfasta.gz" ):
                track = P.snip( os.path.basename( infile ), ".csfasta.gz" )
                quality = P.snip( infile, ".csfasta.gz" ) + ".qual.gz"
                if not os.path.exists( quality ):
                    raise ValueRerror( "no quality file for %s" % infile )
                statement.append(  """gunzip < %(infile)s 
                                      > %(tmpdir_fastq)s/%(track)s.csfasta""" % locals() )
                statement.append(  """gunzip < %(quality)s 
                                      > %(tmpdir_fastq)s/%(track)s.qual""" % locals() )
                fastqfiles.append( ("%s/%s.csfasta" % (tmpdir_fastq, track),
                                    "%s/%s.qual" % (tmpdir_fastq, track) ) )
                self.datatype = "solid"

            elif infile.endswith( ".fastq.1.gz" ):

                track = P.snip( os.path.basename( infile ), ".gz" )
                track = P.snip( infile, ".fastq.1.gz" )
                infile2 = "%s.fastq.2.gz" % track
                if not os.path.exists( infile2 ):
                    raise ValueError("can not find paired ended file '%s' for '%s'" % (infile2, infile))
                statement.append( """gunzip < %(infile)s 
                                     | python %%(scriptsdir)s/fastq2fastq.py --change-format=sanger --guess-format=phred64 --log=%(outfile)s.log
                                     > %(tmpdir_fastq)s/%(track)s.1.fastq;
                                     gunzip < %(infile2)s 
                                     | python %%(scriptsdir)s/fastq2fastq.py --change-format=sanger --guess-format=phred64 --log=%(outfile)s.log
                                     > %(tmpdir_fastq)s/%(track)s.2.fastq
                                 """ % locals() )
                fastqfiles.append( ("%s/%s.1.fastq" % (tmpdir_fastq, track),
                                    "%s/%s.2.fastq" % (tmpdir_fastq, track) ) )
            else:
                raise NotImplementedError( "unknown file format %s" % infile )

        self.tmpdir_fastq = tmpdir_fastq

        return "; ".join( statement) + ";", fastqfiles

    def mapper( self, infiles, outfile ):
        '''build mapping statement on infiles.
        '''
        return ""
    
    def postprocess( self, infiles, outfile ):
        '''collect output data and postprocess.'''
        return ""

    def cleanup( self, outfile ):
        '''clean up.'''
        statement = '''
        rm -rf %s;
        ''' % (self.tmpdir_fastq)
        
        return statement

    def build( self, infiles, outfile ):
        '''run mapper.'''

        cmd_preprocess, mapfiles = self.preprocess( infiles, outfile )
        cmd_mapper = self.mapper( mapfiles, outfile )
        cmd_postprocess = self.postprocess( infiles, outfile )
        cmd_clean = self.cleanup( outfile )
        
        assert cmd_preprocess.strip().endswith(";")
        assert cmd_mapper.strip().endswith(";")
        assert cmd_postprocess.strip().endswith(";")
        assert cmd_clean.strip().endswith(";")

        statement = " checkpoint; ".join( (cmd_preprocess, 
                                           cmd_mapper,
                                           cmd_postprocess,
                                           cmd_clean ) )

        return statement

class Tophat( Mapper ):
    
    def mapper( self, infiles, outfile ):
        '''build mapping statement on infiles.
        '''

        num_files = [ len( x ) for x in infiles ]
        
        if max(num_files) != min(num_files):
            raise ValueError("mixing single and paired-ended data not possible." )
        
        nfiles = max(num_files)
        
        tmpdir_tophat = os.path.join( self.tmpdir_fastq + "tophat" )
        tmpdir_fastq = self.tmpdir_fastq

        # add options specific to data type
        data_options = []
        if self.datatype == "solid":
            data_options.append( "--quals --integer-quals --color" )
            index_file = "%(bowtie_index_dir)s/%(genome)s_cs"
        else:
            index_file = "%(bowtie_index_dir)s/%(genome)s"

        data_options = " ".join( data_options )

        if nfiles == 1:
            infiles = ",".join( [ x[0] for x in infiles ] )
            statement = '''
            tophat --output-dir %(tmpdir_tophat)s
                   --num-threads %%(tophat_threads)i
                   %(data_options)s
                   %%(tophat_options)s
                   %(index_file)s
                   %(infiles)s 
                   >> %(outfile)s.log 2>&1 ;
            ''' % locals()

        elif nfiles == 2:
            # this section works both for paired-ended fastq files
            # and single-end color space mapping (separate quality file)
            infiles1 = ",".join( [ x[0] for x in infiles ] )
            infiles2 = ",".join( [ x[1] for x in infiles ] )

            statement = '''
            tophat --output-dir %(tmpdir_tophat)s
                   --mate-inner-dist %%(tophat_mate_inner_dist)i
                   --num-threads %%(tophat_threads)i
                   %(data_options)s
                   %%(tophat_options)s
                   %(index_file)s
                   %(infiles1)s %(infiles2)s 
                   >> %(outfile)s.log 2>&1 ;
            ''' % locals()
        else:
            raise ValueError( "unexpected number reads to map: %i " % nfiles )

        self.tmpdir_tophat = tmpdir_tophat

        return statement
    
    def postprocess( self, infiles, outfile ):
        '''collect output data and postprocess.'''
        
        track = P.snip( outfile, ".bam" )
        tmpdir_tophat = self.tmpdir_tophat

        statement = '''
            mv %(tmpdir_tophat)s/accepted_hits.bam %(outfile)s; 
            gzip < %(tmpdir_tophat)s/junctions.bed > %(track)s.junctions.bed.gz; 
            mv %(tmpdir_tophat)s/logs %(outfile)s.logs;
            samtools index %(outfile)s;
            ''' % locals()

        return statement

class BowtieTranscripts( Mapper ):
    '''map with bowtie against transcripts.'''

    def mapper( self, infiles, outfile ):
        '''build mapping statement on infiles.

        .. note:: a filter on bamfiles removes any /1 and /2
            markers from reads. The reason is that these
            markers are removed for paired-end data, but
            not for single-end data and will cause
            problems using read name lookup.
        '''

        num_files = [ len( x ) for x in infiles ]
        
        if max(num_files) != min(num_files):
            raise ValueError("mixing single and paired-ended data not possible." )

        nfiles = max(num_files)

        # transpose files
        infiles = zip( *infiles )

        # add options specific to data type
        data_options = []
        if self.datatype == "solid":
            data_options.append( "-f -C" )
            if nfiles == 2:
                # single end,
                # second file will colors (unpaired data)
                data_options.append( "--quals %s" % ",".join( infiles[1] ) )
                nfiles -= 1
            elif nfiles == 4:
                data_options.append( "-Q1 %s -Q2 %s" % (",".join(infiles[2], infiles[3])) )
                nfiles -= 2
            else:
                raise ValueError( "unexpected number of files" )
            index_prefix = "%(prefix)s_cs"
        else:
            index_prefix = "%(prefix)s"

        data_options = " ".join( data_options )
        tmpdir_fastq = self.tmpdir_fastq

        if nfiles == 1:
            infiles = ",".join( infiles[0])
            statement = '''
                bowtie --quiet --sam
                       --threads %%(bowtie_threads)i
                       %(data_options)s
                       %%(bowtie_options)s
                       %(index_prefix)s
                       %(infiles)s
                       2>%(outfile)s.log
               | awk -v OFS="\\t" '{sub(/\/[12]$/,"",$1);print}'
               | samtools import %%(reffile)s - %(tmpdir_fastq)s/out.bam 1>&2 2>> %(outfile)s.log;
            ''' % locals()

        elif nfiles == 2:
            infiles1 = ",".join( infiles[0] )
            infiles2 = ",".join( infiles[1] )

            statement = '''
                bowtie --quiet --sam
                       --threads %%(bowtie_threads)i
                       %(data_options)s
                       %%(bowtie_options)s
                       %(index_prefix)s
                       -1 %(infiles1)s -2 %(infiles2)s 
                       2>%(outfile)s.log
               | samtools import %%(reffile)s - %(tmpdir_fastq)s/out.bam 1>&2 2>> %(outfile)s.log;
            ''' % locals()            
        else:
            raise ValueError( "unexpected number reads to map: %i " % nfiles )

        return statement

    def postprocess( self, infiles, outfile ):
        '''collect output data and postprocess.'''
        
        track = P.snip( outfile, ".bam" )
        tmpdir_fastq = self.tmpdir_fastq

        statement = '''
             samtools sort %(tmpdir_fastq)s/out.bam %(track)s;
             samtools index %(outfile)s;
             ''' % locals()

        return statement
