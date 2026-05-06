# FLAME

**Fluorescence XAFS Multi-Element Processor**

A GUI application for processing fluorescence XAFS data from multi-element Ge detectors. FLAME reads Bluesky HDF5 files and provides interactive tools for spectrum visualization, channel calibration, peak fitting, deadtime correction, element merging, and export to Athena `.prj` and `.dat` formats.

## Installation

Install the core library (for scripting/headless use):

```bash
pip install flame-xafs
```

Install with the GUI:

```bash
pip install "flame-xafs[gui]"
```

## Usage

### GUI

```bash
flame
```

or

```bash
python -m flame
```

### Python API

```python
from flame import HdfData

data = HdfData("scan.hdf")
data.calibrate_linear(ref_element=0)
results = data.batch_extract(
    bg_lo=2000, bg_hi=2250,
    peak_lo=2080, peak_hi=2180,
    apply_cal=True, apply_dt=True, use_bkg=True,
)
```

## Features

- Load and browse Bluesky HDF5 scan files
- Per-element XRF spectrum visualization with deadtime factors
- Two-peak linear channel calibration across all detector elements
- Gaussian peak fitting with linear background subtraction
- ROI sum extraction (no background model)
- Batch extraction across all energy points
- Automatic edge-energy detection for element flagging
- Merge selected elements and export to `.dat` or Athena `.prj`
- Batch processing of multiple HDF files with shared parameters

## Dependencies

**Core:** numpy, scipy, h5py

**GUI:** wxPython, wxmplot, matplotlib, xraylarch

## License

BSD-3-Clause
