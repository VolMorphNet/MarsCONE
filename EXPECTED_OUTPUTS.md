# Expected Outputs

## Overview

The MarsCONE pipeline generates a comprehensive set of outputs organized by processing module. All outputs are saved in hierarchical directories under `data/test_set/output/`. The pipeline processes digital elevation models (DEMs) of volcanic cones through three sequential stages: generation, detection, and analysis.

## Directory Structure

```
data/test_set/output/
├── generator/              # Module 1: DEM processing & profile generation
│   ├── dem/
│   │   ├── cropped/        # Cropped DEM rasters for each cone
│   │   └── slope/          # Slope gradient rasters
│   └── profiles/
│       ├── whole/          # Full elevation profiles (8 directions per cone)
│       └── cropped/        # Cropped profiles
├── finder/                 # Module 2: Feature detection
│   └── finder_method.csv   # Detected feature coordinates and properties
├── analyzer/               # Module 3: Morphometric analysis
│   ├── cone_summary.csv    # Summary statistics per cone
│   ├── results.csv         # Detailed measurements for all features
│   ├── marscone.gpkg       # GeoPackage with all geometric features
│   └── shapes/             # Vector outputs (GeoPackage format)
│       ├── centers.gpkg              # Detected cone centers
│       ├── centers_input.gpkg        # Input point locations
│       ├── centers_hybrid.gpkg       # Hybrid center detection results
│       └── concave_cones.gpkg        # Concave cone geometries
└── figures/                # Generated visualizations (optional)
    └── test_set/
        └── cross_sections/ # Cross-section plots per cone
```

## Module-Specific Outputs

### Generator Module (`generator/`)

**DEM Outputs:**
- **Cropped DEMs** (`dem/cropped/cone_*.tif`): 
  - GeoTIFF raster files, one per analyzed cone
  - Spatial reference system preserved from original DEM
  - Typical size: 100×100 to 500×500 pixels per cone
  - Example: `cone_1_dem.tif`, `cone_10_dem.tif` (58 files for test dataset)

- **Slope Rasters** (`dem/slope/cone_*_slope.tif`):
  - Calculated slope gradients (degrees or percent)
  - Used for cone boundary identification

**Profile Outputs:**
- **Full Profiles** (`profiles/whole/profile_*_*deg.csv`):
  - Elevation profiles in 8 cardinal/intercardinal directions (0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°)
  - CSV format with columns: `distance` (m), `elevation` (m)
  - One file per cone per direction (8 profiles × N cones)
  - Example: `profile_1_0deg.csv`, `profile_24_90deg.csv`

- **Cropped Profiles** (`profiles/cropped/profile_*_*deg_cropped.csv`):
  - Profiles trimmed to cone extent boundaries
  - Same format as full profiles

### Finder Module (`finder/`)

**Detection Output:**
- **finder_method.csv** (single file):
  - Tabular results of cone feature detection
  - Columns: cone ID, detected feature coordinates (x, y), feature type, detection confidence metrics
  - Records: One entry per detected feature per cone
  - Used as input for morphometric analysis in analyzer module

### Analyzer Module (`analyzer/`)

**Summary Statistics:**
- **cone_summary.csv**:
  - One row per analyzed cone
  - Columns: cone ID, base diameter, height, volume, slope angle, cone morphology classification
  - Summary-level statistics for publications and meta-analyses

**Detailed Measurements:**
- **results.csv** (primary output):
  - Comprehensive morphometric measurements
  - Columns include: cone ID, center location (x, y), base dimensions, height, volume, slope metrics, cone shape parameters
  - Rows: One entry per cone with complete measurement set
  - **This is the main quantitative output for manuscript tables and analyses**

**Vector Geometries (GeoPackage format, .gpkg):**
- **marscone.gpkg**:
  - Master GeoPackage containing all geometric features
  - Layers: cone boundaries, detected centers, slope profiles

- **centers.gpkg**:
  - Point layer with detected cone centers
  - Attributes: cone ID, x, y coordinates, spatial reference

- **centers_input.gpkg**:
  - Point layer with input reference locations
  - For validation and accuracy assessment against ground truth

- **centers_hybrid.gpkg**:
  - Hybrid center detection combining multiple detection methods
  - Includes confidence metrics for semi-automatic workflows

- **concave_cones.gpkg**:
  - Polygon layer representing concave cone geometries
  - Useful for secondary crater identification

**Visualizations (optional):**
- **figures/test_set/cross_sections/**.
  - PNG or PDF images showing elevation profiles
  - One figure per cone-direction combination
  - Suitable for supplementary materials in publications

## Data Formats

### Raster Data
- **Format**: GeoTIFF (.tif)
- **Coordinate System**: Preserved from input DEM (typically UTM or other projection)
- **Data Type**: Float32 for elevation/slope values
- **Geospatial Reference**: Full geospatial metadata included

### Tabular Data
- **Format**: CSV (comma-separated values)
- **Encoding**: UTF-8
- **Header Row**: Column names included
- **Decimal Separator**: Dot (.)
- **No quotes**: Values unquoted unless containing commas or special characters

### Vector Data
- **Format**: GeoPackage (.gpkg, SQLite-based)
- **Geometry Types**: Point (centers), Polygon (cone boundaries)
- **Coordinate System**: Same as input DEM
- **Advantages**: Platform-independent, supports multiple layers, open standard

## Expected File Counts (Test Dataset: 58 Cones)

| Output Type | File Count | Notes |
|-------------|-----------|-------|
| Cropped DEMs | 58 | One per cone |
| Slope Rasters | 58 | One per cone |
| Full Profiles | 464 | 8 directions × 58 cones |
| Cropped Profiles | 464 | 8 directions × 58 cones |
| Detection CSV | 1 | finder_method.csv |
| Summary CSV | 1 | cone_summary.csv |
| Results CSV | 1 | results.csv |
| GeoPackage Files | 5 | marscone.gpkg + 4 individual .gpkg files |
| **Total Data Files** | **1,052 +** | Plus optional cross-section figures |

## Data Validation

After running the complete pipeline, verify outputs by checking:

```bash
# Check generator outputs
ls -lh data/test_set/output/generator/dem/cropped/ | wc -l
ls -lh data/test_set/output/generator/profiles/whole/ | wc -l

# Check finder output
wc -l data/test_set/output/finder/finder_method.csv

# Check analyzer outputs
wc -l data/test_set/output/analyzer/results.csv
ncols data/test_set/output/analyzer/results.csv

# Verify GeoPackage integrity
ogrinfo data/test_set/output/analyzer/marscone.gpkg
```

## Integration with Publications

### For Tables
- Use **results.csv** for morphometric measurement tables
- Use **cone_summary.csv** for summary statistics
- Filter by cone properties (e.g., height > 100m, volume < 1 km³)

### For Figures
- **Elevation profiles**: Use CSV files with plotting software (Python matplotlib, R ggplot2, etc.)
- **Spatial distributions**: Use GeoPackage layers in GIS software (QGIS, ArcGIS)
- **Cross-sections**: Use pre-generated PNG files or regenerate with custom styling

### For Reproducibility
- Archive the complete `data/test_set/output/` directory
- Include **results.csv** and **marscone.gpkg** as supplementary data
- Document input DEM source and spatial reference system
- Include run_pipeline.py execution log for version/parameter tracking

## Output Size Estimates

| Component | Typical Size | Notes |
|-----------|-------------|-------|
| One Cropped DEM | 300-400 KB | GeoTIFF compressed |
| All Cropped DEMs (58) | ~20 MB | Depends on DEM resolution |
| All Profiles (928 files) | ~25 MB | CSV text files |
| finder_method.csv | 100-500 KB | Depends on detection density |
| results.csv | 50-100 KB | One row per cone |
| All GeoPackages | ~500 KB | Vector data, compact format |
| **Total Output** | **~50-60 MB** | For test dataset |

Larger datasets or higher-resolution DEMs will proportionally increase file sizes, particularly for raster outputs.
