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


class ExifFileWorker():
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


    def get_exif(self, fname):
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
        exifdate = self.process_image_exif_date(self.get_exif(fname))
        exifdate = 'No-Exif' if exifdate is None else exifdate
        return exifdate


class OutputCache(object):
    '''
    A simplistic file-skipping strategy: considers a file already existing if name + size match.
    (Doesn't look at contents.)
    '''
    def __init__(self, outdir: str):
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

    def exists(self, basename, size):
        if not basename in self.exist_files:
            return False
        return size == self.exist_files.get(basename)
    

def is_image(fname):
    return re.match(r'.*\.(jpeg|jpg|heic|png|dng)', fname, re.IGNORECASE)

def build_queue(dir: str, outputcache: OutputCache):
    log.info("Processing dir: " + dir)
    filequeue = Queue(maxsize=0)

    for file in glob.iglob(dir + '/**', recursive=True):
        fpath = Path(file).absolute()
        if fpath.is_dir():
            continue
        if not is_image(fpath.as_posix()):
            log.warning('Skipping file: %s' % fpath)
            continue

        basename, basesz = fpath.name, fpath.stat().st_size
        if outputcache.exists(basename, basesz):
            # we already have a file with same name and size: good enough
            log.info("Skip existing file: %s" % (fpath))
            continue

        filequeue.put(fpath.as_posix())
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
    argp.description = '''photo_reorganize aims to create a "shadow" directory structure to organize, by date, 
    all the original photos detected in your macOS Photos Library.

    It does this by crawling an input directory (e.g. the entire Apple Photos Library) on disk, 
    extracting photo creation dates from EXIF data, 
    then creating a folder-per-day output directory structure where each photo is a hardlink to the 
    original photo in the source directory.
    '''
    argp.add_argument('--dir', type=str, help='input directory (e.g. Photos Library originals)', default='.')
    argp.add_argument('--outdir', type=str, help='output directory', default='./out')
    args = argp.parse_args()

    curdir = os.path.expanduser(args.dir)
    wr_dir = os.path.expanduser(args.outdir)
    outputcache = OutputCache(wr_dir)
    filequeue = build_queue(curdir, outputcache)
    output_queue = Queue(maxsize=0)

    threads = []
    for i_thread in range(12):
        worker = ExifFileWorker(filequeue, output_queue)
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
    