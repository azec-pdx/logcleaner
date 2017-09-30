# PII Log Redaction (logcleaner.py)

### Problem
--
**Scenario:** One of our customers has been inadvertently uploading sensitive personally-identifying information (PII) to our system over a period of several months. The customer has since realized their mistake and removed the data from the system, but some of that information was reflected in debugging logs enabled on the system and will need to be removed. The logs in question are archived to a central location and compressed with the gzip utility.

**Scope/Assumptions:** We are only concerned with the archived logs. Backups, application data and any other storage locations may assumed to have been addressed separately. You may assume that each line of each input log file contains data from one and only one customer record. All relevant log files may assumed to be local to the script being run (i.e. located on the same system).

**Requirements:**

- The solution must accept as input one or more text log files that have been compressed with the gzip algorithm.
- For each input file, the solution must produce a redacted copy of the file that has been compressed with the gzip algorithm.
- The solution must also create an audit log that includes the name of each file processed, a count of the total number of lines processed in each log file, and a count of the total number of lines redacted from each log file. The audit log may additionally contain any other information you feel is pertinent. The audit log must not contain any information from the redacted lines.
- The solution must not alter logs in-place, as we will want to verify that they have not been corrupted before replacing the originals.
- The solution must redact all log lines containing sensitive data as identified in the sample data provided.
- The solution must contain clear code comments explaining its usage and internal operations.
- The solution must be able to reliably process hundreds or thousands of log files containing 512 MiB or more of uncompressed log entries per file.

**Preferences:**

- The ideal solution will be cognizant of CPU, RAM and storage limitations and strive to use said resources efficiently while still processing log files as quickly as possible.
- The ideal solution will preserve as much metadata (e.g. date/time stamps, file ownership, file permissions, etc.) as possible from the original log files in the redacted copies.
- The ideal solution will be flexible enough to address similar needs in the future with minimal rework.

**Example Data:**

- File logfile_small.txt.gz contains very basic sample of data. It can be used for program correctness testing.
  Some lines in this file contain only Credit Card records, some lines contain SSN sensitive records,
  some lines contain both and some lines contain none.
- File logfile.txt.gz is 3.5M GZIP archive. It compresses 518M big logfile that contains PII.
  This file can be copied numerous times to test program execution on multiple "large" files.

### Solution
--

####Design

- Python language is selected for solution because of it's rich API for text processing and ease of use
- For purposes of RAM optimization (avoiding reading large files), solution is using memory mapping technique to map large files in address space of the running process. This allows for memory files to behave like both strings and like file objects. For this purpose solution utilizes Python's `mmap` module.
- Python's `mmap` module allows us to use the operating system's virtual memory to access the data on the filesystem directly. Instead of making system calls such as *open*, *read* and *lseek* to manipulate a file, memory-mapping puts the data of the file into memory which allows us to directly manipulate files in memory. This greatly improves I/O performance.
- Solution is optimized to write bare minimum of the data. That data consists of strings **SSN="xxx-xx-xxxx"** and **CC="xxxx-xxxx-xxxx-xxxx"** that are used to redact original sensitive Credit Card and SSN records. Solution accomplishes these minimal writes by using pivots to track matching CC and SSN record positions in each line and then applying `mmap`'s slicing techniques to flush sensitive data record masks to the file. 
- Solution is considerate of the following cases for sensitive data:
  - SSN record found standalone in the log line
  - CC record found standalone in the log line
  - both CC and SSN record's are found in the log line
  - none of the two record's are found in the log line
- One compromise that solution does is decompressing of the input GZIP archives. This is done because it is not possible to memory-map GZIP archive and then work on sensitive data matching over compressed data. However, solution strives to complete decompression in optimal way by utilizing system calls. While doing this, solution attempts to keep all file metadata properties on decompressed files.
- Because of the previously described compromise, solution assumes that there is enough storage space available for each log file to be decompressed
- Program is designed to utilize Python's multiprocessing modules to achieve parallelization in log data processing. Ideally, for each GZIP logfile passed as input argument to program, script will spawn a new process dedicated for redaction of that particular file that will be executed by individual CPU core. In case where the number of GZIP logfiles passed at program's input is larger than actual number of CPU cores, it is left to OS to schedule processes of all remaining files to available cores.
- Other lower-level design considerations can be found in [logcleaner.py](https://github.com/ZeKoU/logcleaner/blob/master/logcleaner.py) module's docstring.

####Running program

Prerequisite for running this program is to have Python version `2.7.*` installed on your local machine. 

#####Running on a small data sample

To run this script on small data set use following steps.

1. Clone this project to local directory by running:
   	
   	```
   	git clone https://github.com/ZeKoU/logcleaner.git
   	```
2. Move to cloned project directory by running:

   ```
   cd logcleaner
   ```
3. Run program on small sample log data file by running:
   
   ```
   python logcleaner.py logfile_small.txt.gz
   ```

After the execution of script is done, you should be able to:

* Assure that program has created `redacted.log` file, logging all lines that were redacted
* Assure that program has created `logfile_small.txt.gz.audit` file, which contains audit metadata including
  - Total number of lines processed
  - Total number of lines redacted
  - Total number of lines with Credit Card data redacted
  - Total number of lines with SSN data redacted
  - Total time spent redacting
* Assure that program has created `logfile_small.txt.redacted.gz` file, which contains redacted data
* Assure that the original file `logfile_small.txt.gz` is un-affected by script's execution

After script completes running, your filesystem should look similar to following:

![Testing script running on small file](https://github.com/ZeKoU/logcleaner/raw/master/images/Filesystem_logcleaner.png)


#####Running on a larger data sample

If you would like to test script execution on larger dataset, you might find file `logfile.txt.gz` useful. 

To run this program on multiple large files, use following steps.

1. Replicate `logfile.txt.gz` file to multiple other files by running this one line command in your console:
   
   ```
   for file in logfile2.txt.gz logfile3.txt.gz logfile4.txt.gz logfile5.txt.gz; do cp logfile.txt.gz "$file" ; done
   ```
2. Run program on 5 GZIP archives by running:
   
   ```
   python logcleaner.py logfile.txt.gz logfile2.txt.gz logfile3.txt.gz logfile4.txt.gz logfile5.txt.gz
   ```

**Performance:**

Running file on 5 GZIP archives shows following performance.

Log file name | Compressed size | Uncompressed size | Lines in logfile | Total lines redacted | SSN redacted lines | CC redacted lines | Time spent redacting |
------------- | ---------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- |
`logfile.txt.gz` | 3.5M | 518M | 3657150 | x | x | x | x |
`logfile2.txt.gz` | 3.5M | 518M | 3657150 | x | x | x | x |
`logfile3.txt.gz` | 3.5M | 518M | 3657150 | x | x | x | x |
`logfile4.txt.gz` | 3.5M | 518M | 3657150 | x | x | x | x |
`logfile5.txt.gz` | 3.5M | 518M | 3657150 | x | x | x | x |

Running this program for  *MacBook Pro (Mid 2015)* with *2.2 GHz Intel Core i7* CPU and *16 GB RAM* shows following utilization of CPU, Memory and I/O


![CPU utilization](https://github.com/ZeKoU/logcleaner/raw/master/images/CPU.png) Each process (running on individual core) is effectively utilizing up to 98.7% CPU

![Memory utilization](https://github.com/ZeKoU/logcleaner/raw/master/images/Memory.png) RAM utilization remains constant at all times while script is running

![I/O performance](https://github.com/ZeKoU/logcleaner/raw/master/images/IO.png) I/O performance chart shows that number of reads remains very low over longer time. This is primarily due to the fact that no data is read once the logfile is memory-mapped. Number of writes is slightly heavier and it comes from the fact that logfiles in  their nature are dense with PII data. However these writes are optimized by using `mmap` module slicing technique.



