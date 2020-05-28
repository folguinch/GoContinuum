# GoContinuum

This program uses an asymmetric sigma clip algorithm to find line-free channels
in the spectrum of the maximum of a data cube. It then uses these channels to
produce a continuum subtracted ms and quality assurance continuum images. 

## Requirements

### Dependencies

In addition to the most recent version of CASA, the code need the following 
python packages:
* numpy
* scipy
* matplotlib
* astropy

### Data structure

The main program runs from the `goco` script. It requires the input data
to be in the following directories:
* `uvdata` for the split visibilities ms.
* `dirty` for the dirty FITS files separated by spectral windows (in some cases 
  in CASA format, see below). The spectral window must be included in the file 
  name, with the substring `.spw[0-3].`. If the `dirty` directory does not exist
  or is empty, dirty files are calculated from each visibility ms in `uvdata`. 
  **IMPORTANT** `goco` checks for FITS files in the `dirty` directory with the 
  same root as the ms. If the naming is different then you can skip the dirty 
  checking step using the option `--skip DIRTY` when calling `goco`. Parameters
  for producing the dirty images are defined in the configuration file (see
  below)

In both cases the file names have to start with:
* `<field_name>` if the observations have 1 EB.
* `<field_name>.<EB_number>` if the observations have more than 1 EB. The EB
  numbering starts from 1.
The visibility files must end with `.ms`

By default these directories should be in the upper `BASE` directory, but this 
can be modified using the command line flag `-b BASE` or `--base BASE`. 
A configuration file named `<field_name>.cfg` needs to be created in
the `BASE` directory (see below for details about this file).

All the directories with the products (e.g. plots) are created by the script if
needed.

## Algorithm implementation

Applying a calibration table from e.g. self-calibration can be applied before or
within the code.

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
- [x] Apply calibration table if needed.
- [x] If more than 1 EB, concatenate the visibilities.
- [x] Use YCLEAN with the continuum subtracted visibilities.

For continuum then:
- [x] Split the visibilities and average channels:
    1. Split using the channels in the mask (files with `cont_avg`).
    2. Split without any masking (files with `allchannels_avg`).
- [x] Apply calibration table if needed.
- [x] If more than 1 EB, concatenate the visibilities.
- [x] Make quality control images using automatic PB cleaning for both
  visibility sets above.

## Basic usage

To apply the algorithm above is as easy as running:
```bash
./goco <field_name>
```

If there are more than 1 EB in the observations, then run:
```bash
./goco --neb <number_of_ebs> <field_name>
```

The program will automatically run all the steps, and if the files already exist
it will overwrite or delete them. If only a specific step has to be run (e.g.
the last CLEAN), then it is recommended to delete the files manually and run:
```bash
./goco --noredo [--neb <number_of_ebs>] <field_name>
```

It is possible to run the program at a specific position with:
```bash
./goco --pos <x pixel> <y pixel> <field_name>
```
**IMPORTANT 1:** the positions are zero based.

**IMPORTANT 2:** different positions for each EB has not been implemented. The
recommendation is to produce images with the same size and pixel size for each
EB if using this method.

### Command line options:
```bash
Usage: goco [-h|--help] [--noredo] [-s|--silent] [--vv] [--dirty] [--skip step [step ...]] [--put_rms] [--pos x y] [--max] field

Parameters:
  field                 Field name

Options:
  -h, --help            Help
  --neb                 Number of EBs
  --noredo              Skip steps some steps already finished
  -s, --silent          Set verbose=0 in pipeline.sh
  --vv                  Set verbose level to debug
  --dirty               Compute dirty images if dirty directory does not exist
  --skip                Skip given steps (see --steps)
  --steps               List available steps
  --put_rms             Put rms in image headers
  --pos                 Position where to extract spectrum
  --max                 Use max to determine position of peak
```
Skip steps values are: `DIRTY`, `AFOLI`, `CONTSUB`, `SPLIT`, `YCLEAN` and `PBCLEAN`.


## The `cfg` file

An example file is in the example directory. The configuration file 
**<field name>.cfg** must follow the following example:
```INI
[DEFAULT]
field = field_name
imsize = 1920 1920
cellsize = 0.03arcsec
spws = 0,1,2,3

[dirty]
robust = 2.0
parallel = true

[afoli]
flagchans = 12~20 30~40
levels = 0.03 0.05 0.1 0.15 0.20 0.25
level_mode = linear

[split_ms]
datacolumn = data

[lineapplycal]
gaintable = phase.cal

[contapplycal]
gaintable = amp.cal

[pbclean]
pbmask = 0.2

[yclean]
vlsr = 0.0
dir = /dir/to/yclean
chanranges = 0~1930 1910~3839
joinchans = 0~1920 11~1929
```

Parameters in the `DEFAULT` section are applied to all the other sections if 
not specified within the section.
If selfcal has not been applied or comes from a split file, then `datacolumn` 
should be set to `data`. 

The `flagchans` in `afoli` allows the addition of specific flags for channels.
If the `levels` pararmeter is included, the program will calculate the channels
masked at these levels. The channels with valid data are determined where 
`continuum[i]/final_continuum == 1+levels[j]` where `continuum[i]` is the continuum
from iteration `i` of the `sigma_clip` function. The kind of interpolation between
iterations can be controled with `level_mode`.

Self-calibration tables can be applied after the `uvcontsub` and `split` steps 
for lines and continuum respectively. For more than one eb observations and each
with its own calibration table then there are 2 ways to specify the calibration
tables. For example, observations with an EB with 2 calibration tables and other 
EB with 1, the first alternative is:
```INI
[lineapplycal1]
gaintable = eb1.table1.cal eb1.table2.cal

[lineapplycal2]
gaintable = eb2.table1.cal
```
or
```INI
[lineapplycal]
gaintable = eb1.table1.cal eb1.table2.cal, eb2.table1.cal
```

The `chanranges` parameter will split the data in different cubes, whilst 
`joinchans` are the channels used to join these cubes. These can be 
ommited if the data won't be splitted into smaller cubes. The `vlsr` is in
km/s. Rest frequencies for each spectral window in `spw` can be given with
the `restfreqs` parameter in the `yclean` section.

If there are spectral windows with different sizes then the `yclean` section 
can take values of `chanranges` and `joinchans` for each spw. For example, if
there are 2 spws, the first one with 3840 channels and want to split it in 
around half, and the second one with 1920 channels and use all the channels, 
then the yclean section would look like:
```INI
[yclean]
spws = 0,1
vlsr = 0.0
dir = /dir/to/yclean
freqs = 234.525GHz 232.025GHz
chanrange0 = 0~1930 1910~3839
joinchans0 = 0~1920 11~1929
```

