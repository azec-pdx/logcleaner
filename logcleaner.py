'''
logcleaner.py is a module that redacts sensitive information with following assumptions:

1. Log files for redacting are passed as a list of arguments
2. Each log file is compressed as GZIP archive
3. When uncompressed, each logfile that needs redacting is 512MB+ (this is what is considered by large file in this context)
4. Each line of each input log file contains data from one and only one customer record
5. Based on 4. it is assumed there can be only one SSN and CC data entry per line of log file
6. As solution is using memory-mapping techniques, it needs to decompress data on the filesystem in order to be able to write that data in-place
7. Based on 6. solution assumes that there is enough storage space available for each log file to be decompressed for redaction processing
8. Redaction is based on minimum-write operations by using mmap slicing techniques
9. Search of sensitive data is based on Regular Expressions
10. RegEx for Credit Card assumes that all Credit Card sensitive entries are of the form CC="nnnn-nnnn-nnnn-nnnn" where there is total of 16 digits separated by -
11. RegEx for SSN assumes that all SSN sensitive entries are of the form SSN="mmm-mm-mmmm" where there is total of 9 digits separated by -
12. It doesn't starve RAM memory, it mostly remains constant because of mmap
13. It tries to utilize each CPU core to the maximum (within OS boundaries)
14. It is not I/O intensive based on bare-minimum of writes of data that needs to be masked (redacted)
15. It logs debug data in local file 'redacted.log'
16. It creates audit file containing redaction metadata. Each audit file has same name as file processed with suffix ".audit"
'''

import time
import sys
import logging
import gzip
import shutil
import multiprocessing as mp
import re
import mmap
import os
from datetime import timedelta
from subprocess import check_call

#Log file produced by this program
LOG_FILE = 'redacted.log'

#Configure simplest logger
logging.basicConfig(filename=LOG_FILE,
                    level=logging.DEBUG,
                    format='%(name)s (%(levelname)s) %(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')
LOG = logging.getLogger(__name__)

# Credit Card RegEx used to match CC="1111-2222-3333-4444" for example
cc_pattern = re.compile(r'(CC="\d{4}[\-]{1}\d{4}[\-]{1}\d{4}[\-]{1}\d{4}")')
# Social Security Number RegEx to match SSN="111-22-3333" for example
ssn_pattern = re.compile(r'(SSN="\d{3}[\-]{1}\d{2}[\-]{1}\d{4}")')
# Masks used to replace sensitive Credit Card & SSN data entries
CC_REPLACE_STR = 'CC="xxxx-xxxx-xxxx-xxxx"'
SSN_REPLACE_STR = 'SSN="xxx-xx-xxxx"'

#Dictionary keys for audit metadata
TOTAL_LINES_PROCESSED = 'total_lines_processed'
TOTAL_LINES_REDACTED = 'total_lines_redacted'
TOTAL_CC_LINES_REDACTED = 'total_cc_lines_redacted'
TOTAL_SSN_LINES_REDACTED = 'total_ssn_lines_redacted'
TOTAL_TIME_REDACTING = 'total_time_redacting'

def clean_files(files_list):
    '''
    Runs redacting workflow on all files in list files_list
    Optimizes processing by scheduling each file to be
    processed by individual CPU core.
    '''
    pool = mp.Pool()
    jobs = []
    for fil in files_list:
        jobs.append( pool.apply_async(clean_file, (fil,)) )
    # Wait for all jobs to finish
    for job in jobs:
        job.get()
    # Clean up
    pool.close()

def clean_file(log_file):
    '''
    Runs workflow of operations to redact log_file

    :param str log_file: Name of the local compressed GZIP file containing sensitive log data
    '''
    LOG.debug('Starting processing on file %s', log_file)
    dec_logfile = decompress_file(log_file) #Decompress .gz archive in order to be able to mmap decompressed data
    audit_metadata_dict = redact_data(dec_logfile) #Redact data using memory mapping
    compress_file(dec_logfile) #Compres redacted file to its own .gz archive (not original)
    log_audit_metadata(dec_logfile, audit_metadata_dict) #Creates and writes audit metadata

def redact_data(dec_logfile):
    '''
    Uses mmap module for in-place editing of potentially very large log files.
    This allows for RAM utilization to remain constant while processing large files.
    This method will try to utilize CPU core to the maximum capacity.
    Designed to do minimum of I/O read & write operations when flushing sensitive data
    segments that need to be redacted(masked).
    The total number of I/O operations will depend only on amount of sensitive
    pieces of data that needs to be redacted.

    This method is designed to work only with 64-bit versions of Python on 64-bit CPUs to enable
    memory mapping of very large files into process address space.
    Redacts only log lines which contain Credit Card or SSN sensitive data.

    :param str dec_logfile: Decompressed logfile containing sensitive data

    :return dictionary with keys
     where:
        TOTAL_LINES_PROCESSED - Total number of lines processed in file
        TOTAL_LINES_REDACTED - Total number of lines redacted in dec_logfile
        TOTAL_CC_LINES_REDACTED - Total number of Credit Card redactions in dec_logfile
        TOTAL_SSN_LINES_REDACTED - Total number of SSN redactions in dec_logfile
        TOTAL_TIME_REDACTING - Total time spent redacting file dec_logfile
    '''
    start_time = time.time()
    with open(dec_logfile, 'r+') as f: #Open file with r+ (appending mode for inplace editing)
        LOG.debug("Redacting sensitive information on file %s", dec_logfile)
        mm = mmap.mmap(f.fileno(), 0)
        # Rewind to beginning
        mm.seek(0)
        lines_redacted = 0 #Total lines redacted in this file (includes CC & SSN)
        cc_redactions = 0 #Total Credit Card redactions in this file
        ssn_redactions = 0 #Total SSN redactions on this file
        line_count = 1 #Total lines processed in this file

        current_line_offset = mm.tell() #Initial pointer of mmap (starting at 0)
        next_line_offset = mm.tell() #Initial pointer of mmap (starting at 0)

        for line in iter(mm.readline, ""):
            next_line_offset = mm.tell() #After reading the line, offset is set to end of that line

            cc_match = re.search(cc_pattern, line)
            if cc_match:
                (match_start_i, match_end_i) = cc_match.span(0) #Assumes at most one Credit Card record can exist per row (which should make sense if one row is one customer's record)
                LOG.debug("Redacting line %s of file %s containing Credit Card sensitive data. Offset slice [%s, %s]", line_count, dec_logfile, current_line_offset + match_start_i, current_line_offset + match_end_i)
                mm[current_line_offset + match_start_i : current_line_offset + match_end_i] = CC_REPLACE_STR
                cc_redactions += 1
                line = mm[current_line_offset:next_line_offset] #In case there is both CC and SSN record in same line/row, consider re-reading that line with mmap to contain accurate data after CC redaction

            ssn_match = re.search(ssn_pattern, line)
            if ssn_match:
                (match_start_i, match_end_i) = ssn_match.span(0)
                LOG.debug("Redacting line %s of file %s containing SSN sensitive data. Offset slice [%s, %s]", line_count, dec_logfile, current_line_offset + match_start_i, current_line_offset + match_end_i)
                mm[current_line_offset + match_start_i : current_line_offset + match_end_i] = SSN_REPLACE_STR
                ssn_redactions += 1

            if cc_match or ssn_match:
                lines_redacted += 1
                mm.flush() #Make sure data is persisted back to file if there was any redactions on this line only

            current_line_offset = next_line_offset
            line_count += 1

        mm.close() #Close mmap stream

    time_redacting = time.time() - start_time

    LOG.debug("Total lines processed for file %s : %s", dec_logfile, line_count)
    LOG.debug("Total lines redacted for file %s : %s", dec_logfile, lines_redacted)
    LOG.debug("Total lines with SSN redacted for file %s : %s", dec_logfile, ssn_redactions)
    LOG.debug("Total lines with CC redacted for file %s : %s", dec_logfile, cc_redactions)
    LOG.debug("Total time spent redacting file %s: %s", dec_logfile, timedelta(seconds=time_redacting))
    audit_metadata_dict = {TOTAL_LINES_REDACTED:lines_redacted,
                           TOTAL_LINES_PROCESSED:line_count,
                           TOTAL_CC_LINES_REDACTED:cc_redactions,
                           TOTAL_SSN_LINES_REDACTED:ssn_redactions,
                           TOTAL_TIME_REDACTING:timedelta(seconds=time_redacting)}
    return audit_metadata_dict

def decompress_file(comp_logfile_name):
    '''
    Decompresses GZIP file.
    Maintains file properties (date/time stamps, file ownership, file permissions, etc.)

    :return str name of decompressed file
    '''
    dec_logfile_name = os.path.splitext(comp_logfile_name)[0] #Remove .gz suffix from file
    with gzip.open(comp_logfile_name, 'rb') as f_in, open(dec_logfile_name, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
    shutil.copystat(comp_logfile_name, dec_logfile_name)
    return dec_logfile_name

def compress_file(decomp_logfile_name):
    '''
    Compresses log file in GZIP archive.
    Maintains file properties (date/time stamps, file ownership, file permissions, etc.)
    '''
    # Handling zipping with system call as we don't have to touch data
    check_call(['gzip', '-S', '.redacted.gz' , decomp_logfile_name])

def log_audit_metadata(logfile_name, audit_metadata_dict):
    '''
    Creates audit log file by appending ".audit" to the name of logfile_name

    :param str logfile_name: Logfile for which audit metadata log file is being created
    :param dict audit_metadata_dict: Audit metadata relevant for logfile_name
    '''
    filename = logfile_name + '.audit'
    with open(filename, 'a+') as audit_file:
        audit_file.write("Total number of lines processed: " + str(audit_metadata_dict.get(TOTAL_LINES_PROCESSED)) + os.linesep)
        audit_file.write("Total number of lines redacted: " + str(audit_metadata_dict.get(TOTAL_LINES_REDACTED)) + os.linesep)
        audit_file.write("Total number of lines with Credit Card data redacted: " + str(audit_metadata_dict.get(TOTAL_CC_LINES_REDACTED)) + os.linesep)
        audit_file.write("Total number of lines with SSN data redacted: " + str(audit_metadata_dict.get(TOTAL_SSN_LINES_REDACTED)) + os.linesep)
        audit_file.write("Total time spent redacting: " + str(audit_metadata_dict.get(TOTAL_TIME_REDACTING)) + os.linesep)

def main():
    '''
    Main method.
    Runs log redaction on files provided as program arguments
    '''
    num_files = len(sys.argv)
    if num_files < 2:
        LOG.error("Terminating processing! Please provide at least one log file to process!")
        sys.exit()
    else:
        LOG.debug("Starting logs processing.")
        #Pass all arguments as module-local files to process (cleanup)
        clean_files(sys.argv[1:])

if __name__ =='__main__':
    main()
