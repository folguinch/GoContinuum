# GoContinuum

This program uses an asymmetric sigma clip algorithm to find line-free channels
in the spectrum of the maximum of a data cube. It then uses these channels to
produce a continuum subtracted ms and quality assurance continuum images. 

## Requirements

### Dependencies

The code has been tested with [CASA](https://casa.nrao.edu/) 5.x versions and 
python 2.7. In addition the code need the following python packages:
* numpy
* scipy
* matplotlib
* astropy

### Data structure

The main program runs from the `pipeline.sh` script. It requires the input data
to be in the following directories:
* `final_uvdata` for the split visibilities ms.
* `dirty` for the dirty FITS files separated by spectral windows (in some cases 
  in CASA format, see below). The spectral window must be included in the file 
  name, with the substring `.spw[0-3].`.

In both cases the file names have to start with:
* `<field_name>` if the observations have 1 EB.
* `<field_name>.<EB_number>` if the observations have more than 1 EB. The EB
  number starts from 1.

By default these directories should be in the upper directory, but this can be
modified by changing the `BASE` parameter defined at the beginning of the
script. A configuration file named `<field_name>.cfg` needs to be created in
the `BASE` directory (see below for details about this file).

All the directories with the products (e.g. plots) are created by the script if
needed.

## Algorithm implementation

The ms files in `final_uvdata` are assumed to be self-calibrated (i.e. they
have a corrected data column).

For each EB:
- [x] Search for the maximum value in each SWP (neglecting the 10 channels at 
the edges)
- [x] Combine maximum values, reject the one that is an outlier and take the 
average among the other 3 values to define the *central source*.
- [x] Extract the spectra at the *central source*.
- [x] Find the continuum channels from the spetrum of the *central source*:
    1. Mask channels at the edges of the spectrum.
    2. Applying an asymmetrical sigma clip with `sigma_upper=1.3` and 
        `sigma_lower=3.0` to mask channels with lines.
    3. Unmask channels with line emission that span for less than 3 continuous 
        channels (2 *raw* channels correspond to 1 spectral resolution).
    4. Save the mask.

For lines then:
- [x] Run `uvcontsub` (in CASA) for each EB using the mask to subtract the 
    continuum.
- [x] If more than 1 EB, concatenate the visibilities.
- [ ] Use YCLEAN with the continuum subtracted visibilities.

For continuum then:
- [x] Split the visibilities and average channels:
    1. Split using the channels in the mask (files with `cont_avg`).
    2. Split without any masking (files with `allchannels_avg`).
- [x] If more than 1 EB, concatenate the visibilities.
- [x] Make quality control images using automatic PB cleaning for both
  visibility sets above.


## Basic usage

To apply the algorithm above is as easy as running:
```bash
./pipeline.sh <field_name>
```

If there are more than 1 EB in the observations, then run:
```bash
./pipeline.sh --neb <number_of_ebs> <field_name>
```

The program will automatically run all the steps, and if the files already exist
it will overwrite or delete them. If only a specific step has to be run (e.g.
the last CLEAN), then it is recommended to delete the files manually and run:
```bash
./pipeline.sh --noredo [--neb <number_of_ebs>] <field_name>
```
The continuum finding will run either way on the saved spectra.

It is possible to run the program at a specific position with:
```bash
./pipeline.sh --pos <x pixel> <y pixel> <field_name>
```
**IMPORTANT 1:** the positions are zero based.

**IMPORTANT 2:** different positions for each EB has not been implemented. The
recommendation is to produce images with the same size and pixel size for each
EB if using this method.

## The `cfg` file

The configuration file **<field name>.cfg** must follow the following example:
```INI
[field_name]
imsize = 1024 1024
cellsize = 0.04arcsec
```

[![DOI](https://zenodo.org/badge/177511811.svg)](https://zenodo.org/badge/latestdoi/177511811)
