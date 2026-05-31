# MarsCONE Pipeline Runner

Automated orchestration script for running the complete MarsCONE analysis workflow.

## Overview

The `run_pipeline.py` script automates the execution of all MarsCONE modules in the correct sequence:

1. **Generator** (`generator-py/main.py`) - Creates DEM crops, transects, and elevation profiles
2. **Finder** (`finder-py/main.py`) - Detects cone features (bottom, top, center points)
3. **Analyzer** (`analyzer-py/main.py`) - Calculates morphometric parameters
4. **Visualizer** (`cross-section.ipynb`) - Generates plots (optional)

## Quick Start

### Run Complete Pipeline

```bash
# Full pipeline (generator → finder → analyzer)
python run_pipeline.py

# With visualization
python run_pipeline.py --with-viz
```

### Run Individual Steps

```bash
# Only generator
python run_pipeline.py --only-generator

# Only finder (requires generator output)
python run_pipeline.py --only-finder

# Only analyzer (requires finder output)
python run_pipeline.py --only-analyzer
```

### Skip Steps

```bash
# Skip generator (use existing transects/profiles)
python run_pipeline.py --skip-generator

# Skip finder (use existing feature points)
python run_pipeline.py --skip-finder

# Run generator and finder only
python run_pipeline.py --skip-analyzer
```

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--skip-generator` | Skip generator step (use existing data) |
| `--skip-finder` | Skip finder step (use existing features) |
| `--skip-analyzer` | Skip analyzer step |
| `--only-generator` | Run only generator module |
| `--only-finder` | Run only finder module |
| `--only-analyzer` | Run only analyzer module |
| `--with-viz` | Execute visualization notebook after analysis |
| `-h, --help` | Show help message |

## Prerequisites

### Required

- Python 3.8+
- conda environment `marscone` activated:
  ```bash
  conda activate marscone
  ```
- Configuration files:
  - `generator-py/config.json`
  - `finder-py/config.json`
  - `analyzer-py/config.json`
- Input data in `data/test_set/input/`:
  - DEM files (`.tif`)
  - Point shapefiles (`.shp`)

### Optional (for visualization)

```bash
pip install jupyter nbconvert
```

## Usage Examples

### Example 1: First-Time Analysis

Run complete pipeline on new data:

```bash
# Download demo data
python examples/example_download_demo_data.py

# Run full analysis
python run_pipeline.py
```

### Example 2: Re-run Analysis Only

If you've already generated transects and profiles:

```bash
# Skip generator, run finder and analyzer
python run_pipeline.py --skip-generator
```

### Example 3: Update Morphometric Calculations

If feature points are already detected:

```bash
# Run only analyzer with new parameters
python run_pipeline.py --only-analyzer
```

### Example 4: Complete Analysis with Visualization

```bash
# Full pipeline + plots
python run_pipeline.py --with-viz
```

## Output

The script provides:

- **Progress indicators** for each step
- **Execution time** for each module
- **Success/failure status** for each step
- **Summary report** at completion

Example output:

```
╔==========================================================╗
║          MarsCONE Analysis Pipeline                      ║
╚==========================================================╝

============================================================
▶ Running Generator...
============================================================
✔ Generator completed successfully in 7.0s

============================================================
▶ Running Finder...
============================================================
✔ Finder completed successfully in 2.3s

============================================================
▶ Running Analyzer...
============================================================
✔ Analyzer completed successfully in 2.8s

============================================================
Pipeline Summary:
============================================================
  Generator            ✔ PASSED
  Finder               ✔ PASSED
  Analyzer             ✔ PASSED

⏱ Total execution time: 12.2s

✔ Pipeline completed successfully!
```

## Exit Codes

- **0** - All steps completed successfully
- **1** - One or more steps failed

## Integration Testing

The pipeline includes integration tests using real demo data:

```bash
# Run integration tests
python -m pytest tests/test_pipeline_integration.py -v

# Run all tests including integration
python -m pytest tests/ -v
```

### Test Coverage

Integration tests verify:

- Demo data structure
- Input files (DEM, shapefiles, database)
- Output directories created
- Result files generated
- CSV files contain data
- Pipeline runner functionality

## Troubleshooting

### Error: "config.json not found"

**Solution**: Ensure you're running from module directory or config files exist:

```bash
ls generator-py/config.json
ls finder-py/config.json
ls analyzer-py/config.json
```

### Error: "Module failed"

**Solution**: Check module-specific logs:

```bash
# Run module individually to see detailed output
cd generator-py
python main.py
```

### Error: "Jupyter not found" (for --with-viz)

**Solution**: Install Jupyter:

```bash
conda install -c conda-forge jupyter nbconvert
```

### Pipeline stops at specific step

**Solution**: Check input data and configuration:

1. **Generator fails**: Check DEM files and points in `data/test_set/input/`
2. **Finder fails**: Check generator output in `data/test_set/output/generator/`
3. **Analyzer fails**: Check finder output in `data/test_set/output/finder/`

## Manual Execution

If you prefer to run modules manually:

```bash
# Step 1: Generator
cd generator-py
python main.py

# Step 2: Finder
cd ../finder-py
python main.py

# Step 3: Analyzer
cd ../analyzer-py
python main.py

# Step 4: Visualization (optional)
cd ..
jupyter nbconvert --to notebook --execute --inplace cross-section.ipynb
```

## Performance

Typical execution times on test_set dataset (50 cones):

| Module | Execution Time |
|--------|----------------|
| Generator | ~7-10s |
| Finder | ~2-10s |
| Analyzer | ~2-90s |
| **Total** | **~10-110s** |

Times vary based on:
- Number of cones
- DEM resolution
- Number of transects
- System performance

## Related Documentation

- [README_UPDATED.md](README_UPDATED.md) - User guide
- [INSTALL.md](INSTALL.md) - Installation instructions
- [tests/test_pipeline_integration.py](tests/test_pipeline_integration.py) - Integration tests

## Author

MarsCONE Development Team

## Last Updated

2026-02-15
