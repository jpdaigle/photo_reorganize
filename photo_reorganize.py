#! /usr/bin/env python3
import os
import sys
import glob
import re
from queue import Queue, Empty
from threading import Thread
from pathlib import Path
from collections import namedtuple
import subprocess
import argparse
import json
import logging
import glob

logging.basicConfig(level='INFO', stream=sys.stdout)
log = logging.getLogger(__name__)

DatedFile = namedtuple('DatedFile', 'path date')


class FileWorker():
    def __init__(self, filequeue, output_queue = None):
        self.__queue = filequeue
        self.__outputqueue = output_queue

    def run(self):
        while True:
            try:
                fname = self.__queue.get(False)
                if fname is None:
                    break
                fdate = DatedFile(path=fname, date=worker.extract_date(fname))
                log.info(fdate)
                if self.__outputqueue:
                    self.__outputqueue.put(fdate)
                self.__queue.task_done()
            except Empty:
                log.warning('Thread done!')
                break
            except:
                log.warning('Runtime error')
                self.__queue.task_done()


    def process_file(self, fname):
        proc_output = subprocess.run(
            ['exiftool', '-dateFormat',  '%Y-%m-%d', '-json', fname],
            text=True,
            capture_output=True
            )
        
        if proc_output.returncode != 0:
            raise RuntimeError("exiftool failed: " + fname)

        parsed_exif = json.loads(proc_output.stdout)[0]
        return parsed_exif


    def process_image_exif_date(self, exif_props):
        for key in ('DateTimeOriginal', 'CreateDate', 'FileModifyDate'):
            if key in exif_props and re.match('\d{4}-\d{2}-\d{2}', exif_props[key]):
                return exif_props[key]
        return None

    def extract_date(self, fname):
        exifdate = self.process_image_exif_date(self.process_file(fname))
        exifdate = 'No-Exif' if exifdate is None else exifdate
        return exifdate


class OutputCache(object):
    def __init__(self, outdir):
        super().__init__()
        exist_files = {}
        
        for fpath in glob.glob(outdir + '/**', recursive=True):
            P = Path(fpath)
            if not P.is_file():
                continue
            exist_files[P.name] = P.stat().st_size
        self.exist_files = exist_files
        log.info("Loaded output cache: %d files" % len(exist_files))

    def stat(self, basename):
        return self.exist_files.get(basename)
    

def is_image(fname):
    return re.match(r'.*\.(jpeg|jpg|heic|png|dng)', fname, re.IGNORECASE)

def build_queue(dir: str, outputcache: OutputCache):
    log.info("Processing dir: " + dir)
    filequeue = Queue(maxsize=0)

    limit = -1
    for file in glob.iglob(dir + '/**', recursive=True):
        if not is_image(file):
            log.warning('Skipping file: ' + file)
            continue
        abs_filepath = os.path.abspath(file)

        pathobj = Path(abs_filepath)
        basename, basesz = pathobj.name, pathobj.stat().st_size
        if outputcache.stat(basename) == basesz:
            # we already have a file with same name and size: good enough
            log.info("Skip existing file: %s" % (abs_filepath))
            continue

        filequeue.put(abs_filepath)
        limit -= 1
        if limit == 0: break
    return filequeue


def makelinks(detected_file: DatedFile, outputdir: str):
    if not detected_file.path:
        raise ValueError('expected source file path')
    if not detected_file.date:
        raise ValueError('expected exifdate')

    wr_dir = os.path.join(outputdir, detected_file.date)
    if not os.path.exists(wr_dir):
        os.makedirs(wr_dir)
    
    lnk_name = os.path.join(wr_dir, os.path.basename(detected_file.path))

    if os.path.exists(lnk_name):
        log.info('Skipping %s, exists' % lnk_name)
    else:
        log.info("Linking %s => %s" % (detected_file.path, lnk_name))
        os.link(detected_file.path, lnk_name)


if __name__ == '__main__':

    argp = argparse.ArgumentParser()
    argp.add_argument('--dir', type=str, help='directory', default='.')
    argp.add_argument('--outdir', type=str, help='output dir', default='./out')

    args = argp.parse_args()

    #default_dir = '/Users/jpdaigle/Pictures/Photos Library.photoslibrary/originals/5'
    curdir = os.path.expanduser(args.dir)
    wr_dir = os.path.expanduser(args.outdir)
    outputcache = OutputCache(wr_dir)
    filequeue = build_queue(curdir, outputcache)
    output_queue = Queue(maxsize=0)

    threads = []
    for i_thread in range(12):
        worker = FileWorker(filequeue, output_queue)
        th = Thread(target=worker.run)
        threads.append(th)
        th.start()

    log.info('Waiting for exits')
    for th in threads:
        th.join()

    # make all links
    while True:
        try:
            detected_file = output_queue.get_nowait()
            makelinks(detected_file, wr_dir)
        except Empty:
            break
    