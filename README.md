# photo_reorganize

## What it is

`photo_reorganize` aims to create a "shadow" directory structure to organize, by date, all the original photos detected in your macOS **Photos Library**.

It does this by crawling an input directory (e.g. the entire Apple **Photos Library**) on disk, extracting photo creation dates using [`exiftool`](https://exiftool.org/), then creating a folder-per-day output directory structure where each photo is a hardlink to the original photo in the source directory.

In other words:

```
out/
    2020-02-03/
        59DAC689.jpeg ==> hardlink to original
        59DAC690.jpeg ==> hardlink to original
        59DAC691.jpeg ==> hardlink to original

    2020-02-06/
        5EECC719.jpeg ==> hardlink to original

    etc...
```

This approach does not duplicate any files and thus doesn't waste disk space.

## Usage

```
usage: photo_reorganize.py [-h] [--dir DIR] [--outdir OUTDIR]

photo_reorganize aims to create a "shadow" directory structure to organize, by
date, all the original photos detected in your macOS Photos Library. It does
this by crawling an input directory (e.g. the entire Apple Photos Library) on
disk, extracting photo creation dates from EXIF data, then creating a folder-
per-day output directory structure where each photo is a hardlink to the
original photo in the source directory.

optional arguments:
  -h, --help       show this help message and exit
  --dir DIR        input directory (e.g. Photos Library originals)
  --outdir OUTDIR  output directory
```