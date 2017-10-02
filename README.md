# PII Log Redaction (logcleaner.py)

### Problem
<hr>

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

- File `logfile_small.txt.gz` contains a very basic sample of the data, which can be used for program correctness testing.
  Some lines in this file contain only Credit Card records, some lines contain SSN sensitive records,
  some lines contain both and some lines contain neither.
- File `logfile.txt.gz` is 3.5MB GZIP archive, which compresses a 518MB log that contains PII.
  This file can be copied numerous times to test program execution on multiple "large" files.

### Solution
<hr>

#### Design

- The Python language is selected to deliver this solution because of it's rich API for text processing and ease of use.
- For purposes of RAM optimization (to avoid reading large files), the solution is using a memory mapping technique to map large files to an address space of the running process. This allows for memory files to behave like both strings and file objects. For this purpose the solution utilizes Python's `mmap` module.
- Python's `mmap` module allows us to use the operating system's virtual memory to access the data on the filesystem directly. Instead of making system calls such as *open*, *read* and *lseek* to manipulate a file, memory-mapping puts the data of the file into memory, which allows us to directly manipulate files in memory. This greatly improves the I/O performance.
- The solution is optimized to write a bare minimum of the data. That data consists of strings **SSN="xxx-xx-xxxx"** and **CC="xxxx-xxxx-xxxx-xxxx"** that are used to redact original sensitive Credit Card and SSN records. Solution accomplishes these minimal writes by using pivots to track matching CC and SSN record positions in each line and then applies the `mmap`'s slicing techniques to flush record masks to the file. 
- The solution is considerate of the following cases for sensitive data:
  - only a SSN record exists as PII in one log line
  - only a CC record exists as PII in one log line
  - both, a CC and a SSN, records are found in the log line
  - neither of the two records are found in the log line
- One tradeoff done by the solution is the decompressing of the input GZIP archives. This is done because it is not possible to memory-map the GZIP archive and then perform sensitive data matching over the compressed data. However, the solution strives to complete decompression in an optimal way by utilizing system calls. While doing this, the solution attempts to keep all file metadata properties on decompressed files.
- Due to the previously described compromise, the solution assumes that there is enough storage space available for each log file to be decompressed.
- The program is designed to utilize Python's multiprocessing modules to achieve parallelization in the log data processing. Ideally, for each GZIP logfile passed as an input argument to a program, the script will spawn a new process dedicated for redaction of that particular file, which will be executed by an individual CPU core. In cases where the number of GZIP logfiles passed at the program's input is larger than the actual number of CPU cores, it is left to the OS to schedule all processes to the CPU cores as they become available.
- Other lower-level design considerations can be found in [logcleaner.py](https://github.com/ZeKoU/logcleaner/blob/master/logcleaner.py) module's docstring.

#### Running program

A prerequisite for running this program is to have Python version `2.7.*` installed on your local machine. 

##### Running on a small data sample

To run this script on a small data set use the following steps:

1. Clone this project to a local directory by running:
   	
   	```
   	git clone https://github.com/ZeKoU/logcleaner.git
   	```
2. Change the current directory (in the console) to the cloned project's directory by running:

   ```
   cd logcleaner
   ```
3. Start the program on a small sample log data file by running:
   
   ```
   python logcleaner.py logfile_small.txt.gz
   ```

After the execution of the script is done, you should be able to:

* Assure that the program has created `redacted.log` file, which indicates all lines in all files that were redacted.
* Assure that the program has created `logfile_small.txt.gz.audit` file, which contains audit metadata including
  - Total number of lines processed
  - Total number of lines redacted
  - Total number of lines with CC data redacted
  - Total number of lines with SSN data redacted
  - Total time spent redacting
* Assure that the program has created `logfile_small.txt.redacted.gz` file, which contains redacted data
* Assure that the original file `logfile_small.txt.gz` is un-affected by script's execution

After the script is completed, your filesystem should look similar to the following:

![Testing script running on small file](https://github.com/ZeKoU/logcleaner/raw/master/images/Filesystem_logcleaner.png)


##### Running on a larger data sample

If you would like to test the script execution on a larger dataset, you might find the file `logfile.txt.gz` useful. 

To run this program on multiple large files, use the following steps:

1. Replicate the `logfile.txt.gz` file to multiple other files by running this one line command in your console:
   
   ```shell
   for file in logfile2.txt.gz logfile3.txt.gz logfile4.txt.gz logfile5.txt.gz; do cp logfile.txt.gz "$file" ; done
   ```
2. Run the program on a five GZIP archives by running:
   
   ```shell
   python logcleaner.py logfile.txt.gz logfile2.txt.gz logfile3.txt.gz logfile4.txt.gz logfile5.txt.gz
   ```

#### Performance

Running this program on a five GZIP archives shows the performance listed below.

Log file name | Compressed size | Uncompressed size | Lines in logfile | Total lines redacted | SSN redacted lines | CC redacted lines | Time spent redacting |
------------- | ---------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- | ----------------- |
`logfile.txt.gz` | 3.5M | 518M | 3657150 | 417960 | 313470 | 139320 | 4:48:09.385797 |
`logfile2.txt.gz` | 3.5M | 518M | 3657150 | 417960 | 313470 | 139320 | 4:45:54.992287 |
`logfile3.txt.gz` | 3.5M | 518M | 3657150 | 417960 | 313470 | 139320 |  4:40:45.697558 |
`logfile4.txt.gz` | 3.5M | 518M | 3657150 | 417960 | 313470 | 139320 | 4:44:43.368736 |
`logfile5.txt.gz` | 3.5M | 518M | 3657150 | 417960 | 313470 | 139320 |   4:38:06.480686 |

This leads to a conclusion that with this implementation it is possible to redact 518MB of uncompressed log data per 1 CPU core in 4h 43min 31sec (average of the above 5 times).

Above tests were produced by running the program on a *MacBook Pro (Mid 2015)* with *2.2 GHz Intel Core i7* CPU and *16 GB RAM*. This particular processor has 8 independent cores, which can be easily checked by running:

```python
import multiprocessing
multiprocessing.cpu_count()
```

which on this machine returns the following result 

`>>>8`

If we ran a program with 8 input files, each one would get assigned to one core, which leads us to a conclusion that this implementation can process 8*518MB = ~2.6GB of data in 4h 43min 31sec. This equates to 29,257,200 lines being processed with total of 3,343,680 lines being redacted.

Breaking it further, this means that **this implementation can redact  ~1720 lines/sec using 8 CPU cores**

During this run, the Activity Monitor was showing a utilization of CPU, Memory and I/O corroborated in the pictures below.

![CPU utilization](https://github.com/ZeKoU/logcleaner/raw/master/images/CPU.png) Each of the 5 processes were running on an individual core and effectively utilizing up to ~98.4% CPU. This also shows that the solution  stands up the processes for the other 3 remaining cores, however they stay idle as there is no task assigned to them.

![Memory utilization](https://github.com/ZeKoU/logcleaner/raw/master/images/Memory.png) RAM utilization remains constant at all times while the script is running.

![I/O performance](https://github.com/ZeKoU/logcleaner/raw/master/images/IO.png) The I/O performance chart shows that number of reads remains very low over a longer period of time. This is primarily due to the fact that no data is read once the logfile is memory-mapped. Number of writes is slightly heavier which comes from the fact that logfiles are dense in nature with PII data. However, these writes are optimized by using the `mmap` module's slicing technique.



