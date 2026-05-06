# AGENTS.md

## Project Overview

**FLAME** (Fluorescence XAFS Multi-Element Processor) is a Python package for processing fluorescence XAFS data from multi-element Ge detectors.

- **Package name:** `flame-xafs`
- **Import name:** `flame`
- **Build system:** hatchling (src-layout)
- **License:** BSD-3-Clause
- **Repository:** https://github.com/shellydkelly/flame-xafs

## Package Structure

```
src/flame/
  __init__.py       # __version__ + re-exports HdfData
  __main__.py       # python -m flame support
  hdfdata.py        # Core data class (numpy/scipy/h5py only)
  gui.py            # wxPython GUI (optional deps via [gui] extra)
  resources/
    flame_icon.ico  # App icon
```

## Architecture

- **`hdfdata.py`** — Core data layer. Reads Bluesky HDF5 files, provides channel calibration, Gaussian peak fitting, ROI sum extraction, batch extraction, and deadtime correction. Dependencies: numpy, scipy, h5py only.
- **`gui.py`** — wxPython GUI. Uses wxmplot PlotPanel for plotting, xraylarch for pre_edge/Athena export. Dependencies: wxPython, wxmplot, matplotlib, xraylarch (installed via `pip install "flame-xafs[gui]"`).

## Dependencies

- **Core** (always installed): numpy, scipy, h5py
- **GUI** (optional `[gui]` extra): wxPython, wxmplot, matplotlib, xraylarch

## Key Context

- FLAME reads HDF5 files produced by Haven's Xspress3 detector driver (spc-group/haven)
- Uses xraylarch's `pre_edge`, `create_athena`, and `Group` for XAFS processing and Athena export
- The `HdfData` class expects Bluesky-structured HDF5 with `ge_13element` detector data
- Currently targets transfer to `spc-group` GitHub org when permissions allow

## What Remains

- **Testing:** No test suite exists yet
- **CI/CD:** No GitHub Actions workflow
- **PyPI publishing:** `python -m build` + `twine upload dist/*` when ready
- **Transfer to spc-group:** Repo is under `shellydkelly` temporarily
