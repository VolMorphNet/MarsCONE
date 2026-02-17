# MarsCONE Installation Guide

## Prerequisites

Before installing MarsCONE, ensure you have:
- Python 3.8 or higher
- pip (Python package installer)
- System libraries for GDAL/GEOS (for GIS operations)

## System-Specific Setup

### Linux (Ubuntu/Debian)

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    python3-dev

# Set environment variables
export CPLUS_INCLUDE_PATH=/usr/include/gdal
export C_INCLUDE_PATH=/usr/include/gdal
```

### macOS

**Option A: Using Homebrew + pip (Advanced)**
```bash
# Install system dependencies
brew install gdal geos proj

# Then you can use pip with:
pip install -r requirements.txt
```

**Option B: Using conda (Recommended)**
```bash
conda install -c conda-forge gdal geopandas
# Or create full environment:
conda env create -f marscone_env.yml
```

### Windows

**Option 1: Using conda (Recommended)**
```bash
conda create -n marscone python=3.10
conda activate marscone
conda install -c conda-forge gdal geopandas
```

**Option 2: Using OSGeo4W**
- Download OSGeo4W installer
- Install GDAL and dependencies
- Set PATH environment variable

## Installation Methods

### Option 1: Using Conda Environment File (Recommended for Development)

```bash
# Clone repository
git clone https://github.com/VolMorphNet/MarsCONE.git
cd marscone/dev

# Create environment from file
conda env create -f marscone_env.yml

# Activate environment
conda activate marscone

# Verify installation
python -c "import geopandas; import numpy; print('Installation OK')"
```

### Option 2: Using pip requirements.txt (Advanced)

⚠️ **IMPORTANT**: This method requires system GDAL/GEOS libraries installed at OS level. See System-Specific Setup above. NOT recommended for beginners - use Option 1 (conda) instead.

**macOS with Homebrew:**
```bash
# Step 1: Install system GDAL libraries (REQUIRED)
brew install gdal geos proj

# Step 2: Clone and setup
git clone https://github.com/VolMorphNet/MarsCONE.git
cd marscone/dev

# Step 3: Create virtual environment
python -m venv marscone-env
source marscone-env/bin/activate

# Step 4: Install Python packages
pip install -r requirements.txt

# Verify
python -c "import geopandas; import osgeo; print('Installation OK')"
```

**Linux (Ubuntu/Debian):**
After installing system deps (see System-Specific Setup above):
```bash
pip install -r requirements.txt
```

**Why pip method is harder:**
- `osgeo` (GDAL Python bindings) is not on PyPI
- Requires system-level GDAL compilation
- macOS: needs Homebrew or OSGeo4W
- Linux: needs apt packages
- **Recommendation**: Use conda (Option 1) unless you have experience with geospatial dependencies

**Dependency Strategy**: The `requirements.txt` uses flexible versioning (`>=`) to ensure compatibility with PyPI:
- Core scientific packages are pinned at minimum stable versions
- Development tools (black, pylint, flake8, isort, ruff) use `>=` versioning
- For exact reproducibility with pinned versions, use conda with `marscone_env.yml` instead

### Option 3: Hybrid Approach (Conda + pip)

```bash
# Create conda environment (handles System dependencies like GDAL)
conda create -n marscone python=3.10 gdal geopandas rasterio shapely

# Activate
conda activate marscone

# Install pip dependencies
git clone https://github.com/VolMorphNet/MarsCONE.git
cd marscone/dev
pip install -r requirements.txt
```

### Option 4: Development Installation (Recommended)

```bash
# Clone repository
git clone https://github.com/VolMorphNet/MarsCONE.git
cd marscone/dev

# Create environment
conda env create -f marscone_env.yml
conda activate marscone

# Install in development mode (if setup.py exists)
pip install -e .
```

### Option 5: Regular Installation

```bash
pip install -e .
```

## Verification

Test your installation:

```bash
# Python script
python -c "import geopandas; import analyzer; print('Installation OK')"

# Command line - Download demo data
python download_demo_data.py --help

# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_pipeline_integration.py -v

# Run tests with coverage report
pytest tests/ --cov=. --cov-report=html
```

### Testing the Pipeline

```bash
# Download demo data first
python download_demo_data.py

# Run full pipeline
python run_pipeline.py

# Run pipeline with visualization
python run_pipeline.py --with-viz

# Run integration tests
pytest tests/test_pipeline_integration.py -v
```

## Troubleshooting

### GDAL Import Error

**Error**: `ImportError: No module named 'osgeo'`

**Solution**:
```bash
# Linux
pip install gdal==$(gdal-config --version)

# macOS
brew install gdal
pip install gdal --no-cache-dir

# Windows with conda
conda install gdal
```

### Geopandas/Shapely Issues

**Error**: `ImportError: cannot open shared object file`

**Solution**:
```bash
# Reinstall with conda
conda install -c conda-forge geopandas shapely gdal
```

### Memory Issues During Installation

```bash
# Install with lower memory usage
pip install --no-cache-dir geopandas
```

### Python Version Compatibility

MarsCONE requires Python >= 3.8. Check your version:

```bash
python --version

# If needed, create environment with specific Python
conda create -n marscone python=3.10
conda activate marscone
```

## Development Setup

For development:

```bash
# Clone and setup with conda
git clone https://github.com/VolMorphNet/MarsCONE.git
cd marscone/dev
conda env create -f marscone_env.yml
conda activate marscone

# Or with pip (requires conda for GDAL first)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install development dependencies
pip install -e ".[dev]"

# Enable pre-commit hooks (if available)
# pre-commit install

# Run linting
black .
isort .
pylint **.py

# Run tests
pytest tests/ -v --cov
```

## Environment Files Reference

### marscone_env.yml (Conda)

- **Use when**: You want to manage system dependencies (GDAL, GEOS, etc.)
- **Advantages**: Handles compilation issues, platform-specific builds
- **Install**: `conda env create -f marscone_env.yml`
- **Includes**: 
  - System libraries (GDAL, Geopandas, Rasterio)
  - Python packages (numpy, pandas, matplotlib, etc.)
  - Development tools (pytest, pylint, black, isort, flake8, nbconvert)

### requirements.txt (pip)

- **Use when**: You already have system dependencies installed
- **Advantages**: Lightweight, reproducible across systems
- **Install**: `pip install -r requirements.txt`
- **Includes**: All pip-installable packages with pinned versions
- **Note**: Requires Python 3.8+ and system libraries pre-installed

### Choosing Between Them

| Scenario | Recommendation |
|----------|-----------------|
| Fresh installation | Use `marscone_env.yml` |
| Mac/Linux with Homebrew | Use `marscone_env.yml` |
| Windows | Use `marscone_env.yml` |
| Existing conda environment | Use `requirements.txt` |
| Docker/CI/CD | Use both (conda base + pip track) |
| Reproducing exact builds | Use `requirements.txt` for consistency |

## Quick Start After Installation

### 1. Download Demo Data

```bash
# Download and extract demo dataset
python download_demo_data.py

# This creates: data/test_set/ with input/dem/ and input/points/
```

### 2. Run Analysis - Option A: Full Pipeline (Recommended)

```bash
# Run complete pipeline: generator → finder → analyzer
python run_pipeline.py

# With visualization (generates cross-section plots)
python run_pipeline.py --with-viz
```

### 2. Run Analysis - Option B: Individual Modules

```bash
# Step 1: Generator (DEM cropping and transect generation)
cd generator-py
python main.py
cd ..

# Step 2: Finder (cone feature detection)
cd finder-py
python main.py
cd ..

# Step 3: Analyzer (morphometric calculations)
cd analyzer-py
python main.py
cd ..

# Optional: Visualization (cross-section notebook)
jupyter nbconvert --to notebook --execute --inplace cross-section.ipynb
```

### 3. View Results

```bash
# Check output files
ls -la data/test_set/output/analyzer/

# View results
head -20 data/test_set/output/analyzer/results.csv
```

## Getting Help

- **Documentation**: [QUALITY_IMPROVEMENTS.md](QUALITY_IMPROVEMENTS.md)
- **Examples**: See `examples/` directory
- **Issues**: Open GitHub Issues
- **Email**: jakub.sledziowski@usz.edu.pl

## Next Steps

- Read [README.md](README.md) for usage
- Check [examples/](examples/) for tutorials  
- Review [QUALITY_IMPROVEMENTS.md](QUALITY_IMPROVEMENTS.md) for code info
- See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute

---

**Last Updated**: 2026-02-15
