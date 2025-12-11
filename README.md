# MarsCONE: A toolbox for automatic detection of Martian pitted cones morphology 

<img src="https://c5studio.pl/marscone/marscone-logo.png" width="200px">

**MarsCONE** is a command-line tool for **automatic morphometric analysis of cone-like landforms** (e.g. volcanic cones, impact-related features) using digital elevation models (DEMs).

The workflow consists of three main modules:

1. **Generator** – crops DEMs around cones and generates radial transects & elevation profiles  
2. **Finder** – detects characteristic points (bottom, top, center) along each transect  
3. **Analyzer** – aggregates transect-level detections into cone-scale metrics and exports GIS-ready outputs  

The code is written in Python and uses standard geospatial libraries (GDAL, GeoPandas, Rasterio, Shapely).

---

## 1. Installation

### 1.1. Prerequisites

- Conda (Miniconda / Mamba / Anaconda)
- GDAL and PROJ available through `conda-forge` (handled by the environment file)
- Python 3.10 (installed via the env)

### 1.2. Create and activate the environment

From the repository root:

```bash
conda env create -f marscone_env.yml
conda activate marscone
```

The marscone_env.yml file installs:
- gdal
- geopandas
- rasterio
- fiona
- pyproj
- shapely
- pandas
- numpy
- matplotlib
- scikit-image
- tqdm

If you already have an environment, you can also install packages manually:

```bash
conda create -n marscone python=3.10
conda activate marscone
conda install -c conda-forge gdal geopandas rasterio fiona pyproj shapely pandas numpy matplotlib scikit-image tqdm
```

## 2. Repository structure

A minimal layout (simplified):

```bash
marscone/
├─ generator-py/
│  ├─ main.py            # Generator CLI
│  ├─ pgen.py/            # DEM cropping, transects, profiles (imported as `pgen`)
│  └─ config.json        # Generator configuration
├─ finder-py/
│  ├─ main.py            # Finder CLI
│  ├─ finder/             # Shape detections and smooth filter
│  └─ config.json        # Finder configuration
├─ analyzer-py/
│  ├─ main.py            # Analyzer CLI
│  ├─ analyzer/           # Basic functions
│  └─ config.json        # Analyzer configuration
├─ marscone_env.yml      # Conda environment definition
└─ data/                 # Input/Output data (Input - DEM, points, and Outputs)
```

**Important**: Each module reads its own config.json located in its folder:
- generator-py/config.json
- finder-py/config.json
- analyzer-py/config.json


## 3. Data and configuration

A typical project tree under a chosen base directory (configured in config.json) may look like:
```bash
test_set/
├─ input/
│  ├─ dem/                   # Input DEM(s)
│  └─ points/                # Cone center points (for point-based workflow)
├─ db/
│  └─ database.gpkg          # GeoPackage with profiles & detected points
└─ output/
   ├─ generator/             
      ├─ dem/                # Cropped DEM
      ├─ profiles/           # Generated transects in CSV files
   ├─ finder/
   │  └─ finder_method.csv   # Finder detections (bottom/top/center)
   └─ analyzer/
      ├─ results.csv         # Per-transect metrics
      ├─ cone_summary.csv    # Aggregated final cone metrics
      ├─ marscone.gpkg       # Final files with detected points that can be used in GIS
      └─ shapes/             # GeoJSON / GPKG outputs
```

### 3.1. Input data
- DEM file should be in geotif format with coordinates (CRS)
- The shapefile with the same CRS should contain a vector layer of points with the centres of the cones (see example in demo data (section 3.2.)).<br/>
**Important!**<br/>
Each point must have a separate ID. This ID will be used to define the results in the further process. 

![MarsCONE input data](https://c5studio.pl/marscone/input-data.png)

### 3.2. Downloading the demo dataset
A small demo dataset (`test_set`) is provided as a ZIP archive hosted externally on ZENODO repository (~183 MB zip file and ~450 MB unzipped).

Dowload demo set from Zenodo https://doi.org/10.5281/zenodo.17885902 or use script described below.

From the repository root, run:

```bash
conda activate marscone
python download_demo_data.py
```
This will:
	•	create a local data/ directory (if it does not exist),
	•	download test_set.zip from the configured URL,
	•	unpack it into data/test_set,
	•	remove the ZIP file after successful extraction.

After this step, the folder structure will look like:
```bash
data/
└─ test_set/
   ├─ input/
   │  ├─ dem/
   │  │  └─ DTEEC_043987_1825_035521_1825_A01.tif
   │  └─ points/
   │     └─ cones.shp
   └─ output/
```
You can then run the full MarsCONE workflow on this demo set using the default config.json files for Generator, Finder and Analyzer

## 4. Configuration files
### 4.1. Generator configuration (generator-py/config.json)

This config controls DEM cropping, transect generation, and profile extraction.

Example:
```bash
{
  "paths": {
    "base": "../data/test_set",
    "input": {
      "masks": "input/crop",
      "dem": "input/dem",
      "points": "input/points"
    },
    "output": {
      "dem_cropped": "output/generator/dem/cropped",
      "dem_slope": "output/generator/dem/slope",
      "profiles_whole": "output/generator/profiles/whole",
      "profiles_cropped": "output/generator/profiles/cropped"
    },
    "db": "db/database.gpkg"
  },
  "db_layers": {
    "points": "points",
    "transects": "transects",
    "profiles": "profiles",
    "buffers": "buffers",
    "masks": "cones"
  },
  "crs": "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=146.79 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs=True",
  "parameters": {
    "transect_length": 300,
    "profile_resolution": 1,
    "buffer_width": 300,
    "mode": "auto",
    "transect_angle_step": 45
  }
}
```

**Key elements:** 
- paths.base
Root directory for all data related to this run (DEM, masks, outputs, DB).
In this example, the module will operate on data/test_set.
- paths.input
    - masks: polygon masks outlining cones (input/crop inside paths.base)
    - dem: DEM rasters (input/dem)
    - points: optional cone center points (input/points), used depending on mode
- paths.output
    - dem_cropped: where cropped DEM tiles are stored
    - dem_slope: optional slope rasters
    - profiles_whole: full elevation for each transect
    - profiles_cropped: cropped profiles if used by your workflow
- paths.db
    Path to the GeoPackage database, relative to paths.base (here db/database.gpkg).
    - db_layers (layer names inside the GeoPackage):
    - points: point layer (can be used later by Finder/Analyzer)
    - transects: line layer storing transect geometries
    - profiles: line layer with profile geometry/vertices
    - buffers: polygon layer used for cone buffers
    - masks: polygon layer for cone masks (here named cones)
- crs
    Project CRS (here an equirectangular projection for Mars with radius 3,392,593.611 m).
	- parameters
        - transect_length: radial transect length (map units, here 250 m)
        - profile_resolution: spacing of sample points along profiles (here 1 m)
        - buffer_width: buffer radius around masks/points used when cropping DEM
        - mode:
        - "auto" – Generator decides based on available inputs (masks vs points)
            - other modes can be added ("mask", "points")
        - transect_angle_step: angular spacing between transects (here ~5.63° → 64 transects)

### 4.2. Finder configuration (finder-py/config.json)

This config controls where Finder reads/writes data and how it classifies shapes.

Example:
``` bash
{
  "paths": {
    "base": "../data/test_set",
    "db": "db/database.gpkg",
    "output": {
      "results_csv": "output/finder/finder_method.csv"
    }
  },
  "db_layers": {
    "profiles": "profiles",
    "points": "points"
  }
}
```

**Key elements:**   
- paths.base<br/>
    Same base directory as in Generator, so that both work on the same dataset.
- paths.db<br/>
    Path to the GeoPackage (db/database.gpkg relative to paths.base).
- paths.output.results_csv<br/>
    CSV file where Finder will export all detected bottom/top/center points.<br/>
    Default: output/finder/finder_method.csv (inside paths.base).
- db_layers
    - profiles: name of the profile line layer created/populated by Generator
    - points: name of the point layer where Finder will store detected points

### 4.3. Analyzer configuration (analyzer-py/config.json)

This config controls input/output paths for Analyzer, CSV options, CRS, and exporting GeoJSON.

Example:
``` bash
{
  "paths": {
    "base": "../data/test_set",
    "input": {
      "profiles": "output/generator/profiles/whole",
      "points": "output/finder",
      "centers": "input/points"
    },
    "output": {
      "shapes": "output/analyzer/shapes",
      "csv": "output/analyzer/results.csv"
    },
    "db": "db/database.gpkg"
  },
  "csv": {
    "sep": ";"
  },
  "shape": {
    "crs": "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=146.79 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs=True"
  },
  "selected_profiles": [],
  "buffer_distance": 1.0,
  "export_geojson": false,
  "export_summary_gpkg": true
}
```

**Key elements:**
- paths.base 
        Same dataset root as in Generator and Finder.
- paths.input
    - profiles: directory with profile CSVs generated by Generator default: output/generator/profiles/whole
    - points: directory where Finder wrote its CSV - Analyzer expects finder_method.csv inside this folder
    - centers: folder with expert crater center points - default: input/points
- paths.output
    - shapes: directory for Analyzer’s vector outputs (buffers, centers, etc.)
    -	csv: first calculated CSV file (per-transect and/or per-cone metrics).
    -	default: output/analyzer/results.csv
- paths.db<br/>
    Path to the GeoPackage (db/database.gpkg).
- csv.sep<br/>
    CSV separator used when reading/writing profile and results tables (here ";").
- shape.crs<br/>
    CRS used by Analyzer, should match the projection of DEM and vector layers (same Mars equirectangular projection as in Generator).
- classification.shape_threshold<br/>
    Threshold used for simple shape classification (flat/convex/concave). This value should depend on DEM resolution - in test set 1px = 1m. <br/>
    Analyzer compares the mean elevation of the crater centre (`center_elev`) to the mean rim elevation (`top_elev`) using this parameter.
    - if `|center_elev − top_elev| < shape_threshold`  
    → **`flat`**
    - if `center_elev < top_elev` and the absolute difference is ≥ `shape_threshold`  
    → **`concave`** (well-developed crater floor below the rim)
    - if `center_elev > top_elev` and the absolute difference is ≥ `shape_threshold`  
    → **`convex`** (domed summit without a clear depression)<br/>
    If no `shape_threshold` is provided in the Analyzer config, the default value `0.5` m is used.
- selected_profiles<br/>
    List of profile IDs to analyze (empty list means “use all profiles”).
- buffer_distance<br/>
    Buffer radius (map units) used when constructing cone footprints for GIS output.
- export_geojson<br/>
If true, Analyzer exports additional GeoJSON summaries per transect/cone.
If false, only CSV and GeoPackage outputs are produced.
- export_summary_gpkg<br/>
If true, Analyzer exports final GeoPackage with detected points and elipses.
If false, only CSV and GeoPackage outputs are produced.

## 5. Workflow overview

The recommended workflow is:
1.	Generator – prepare cropped DEMs, transects, and elevation profiles
2.	Finder – detect bottom, top, and center points along each transect
3.	Analyzer – compute cone-level metrics and export GIS-ready layers

Because each module has its own config.json, you can:
-	run modules independently (even on different data sets), but you must keep the path chain consistent:
    -	Analyzer’s paths.input.profiles must point to Generator’s profiles_whole output
    -	Analyzer’s paths.input.points must point to Finder’s output folder with finder_method.csv
    -	all modules should share the same paths.base and db paths for a given project

## 6. Module 1 – Generator

``` bash
generator-py/main.py
```

### 6.1. Function

Generator is responsible for:
- reading DEMs, masks and/or points
- cropping DEMs around each cone candidate
- generating radial transects for each cone
- sampling DEM along transects to create elevation profiles
- writing profile geometries and attributes into the GeoPackage

Internally, it uses:
- paths.input.masks for mask-based workflows
- paths.input.points for point-based workflows
- parameters.mode to decide which approach to use (e.g. "auto")

### 6.2. Inputs

Configured in generator-py/config.json:
- DEM raster(s) in paths.input.dem
- cone masks (.shp / .gpkg) in paths.input.masks (for mask-based generation)
- cone center points in paths.input.points (for point-based generation)
- output directories for DEM crops and profiles (paths.output.*)
- GeoPackage database at paths.db

### 6.3. Outputs
- Cropped DEM tiles in paths.output.dem_cropped
- Slope rasters in paths.output.dem_slope (if generated)
- Full profiles in paths.output.profiles_whole
- Optionally cropped profiles in paths.output.profiles_cropped
- GeoPackage layers:
- transects – transect lines
- profiles – profile geometries and sample points
- optionally buffers and masks layers if Generator writes them

### 6.4. Running Generator

From the repository root:
``` bash
conda activate marscone
python generator-py/main.py
```

Example console output:<br/>
```bash
Initializing data structures...
Running in mode: POINTS
Cropping DEM rasters using input geometries (points)...
... clipping DEM by cones: 100%|██████████████| 58/58 [00:01<00:00, 48.19it/s]
Generating transects from points...
✔ Saved 464 transects (every 45°) to layer 'transects' in ../data/test_set/db/database.gpkg
Generating profiles from DEM and transects...
... generating profiles: 100%|██████████████| 464/464 [00:02<00:00, 182.17it/s]
✔ Saved 139085 profile points to layer 'profiles'
✔ Exported profiles as individual CSV files to ../data/test_set/output/generator/profiles/whole
```

## 7. Module 2 – Finder

```bash
finder-py/main.py
```

### 7.1. Function

Finder reads profile points from the GeoPackage and:
- splits each transect into two sides (W/E or N/S)
- detects top points using local peaks and elevation drop analysis
- detects bottom points using an adaptive slope-based algorithm
- assigns a center (C) point to each transect
- applies simple shape classification (using classification.shape_threshold)
- writes results to GeoPackage and CSV

### 7.2. Inputs

Configured in finder-py/config.json:
- paths.base – same dataset root
- paths.db – GeoPackage with at least the profiles layer filled by Generator
- db_layers.profiles – name of the profile layer
- db_layers.points – name of the output point layer for detections

Finder expects:
- profile vertices in the profiles layer of db/database.gpkg, with fields like:
- transect_id, cone_id, distance, elevation, slope, x_geo, y_geo, orientation

### 7.3. Outputs
- Point layer in db/database.gpkg under db_layers.points (e.g. points), containing:
    - type (e.g. W_bottom, E_top, C)
    - transect_id, cone_id
    - coordinates and elevations
    - status flags (accepted/refined/etc., depending on implementation)
- CSV file at paths.output.results_csv (default output/finder/finder_method.csv)

### 7.4. Running Finder

From the repository root:
``` bash
conda activate marscone
python finder-py/main.py
```

Example console output:<br/>
```bash
Detecting base and top:  75%|█████████████▌       | 350/464 [00:01<00:00, 350.17it/s]
[DEBUG] Suspicious top @ 162.0 m (elev -2704.95) — transect 53_315deg. Criteria: close=True, flat=True, rising=False. Skipping.
Detecting base and top:  91%|██████████████████▎  | 422/464 [00:01<00:00, 349.71it/s]
[DEBUG] Suspicious top @ 174.0 m (elev -2705.34) — transect 8_0deg. Criteria: close=True, flat=True, rising=False. Skipping.
[DEBUG] Suspicious top @ 126.0 m (elev -2705.34) — transect 8_180deg. Criteria: close=True, flat=True, rising=False. Skipping.
Detecting base and top: 100%|█████████████████████| 464/464 [00:01<00:00, 342.48it/s]
✔ Saved 2320 points to GPKG layer 'points' and CSV '../data/test_set/output/finder/finder_method.csv'
You can now inspect profile-level detections in QGIS by opening db/database.gpkg and loading the profiles and points layers.
```

The above code contains fragments marked [DEBUG], e.g.
*[DEBUG] Suspicious top @ 162.0 m (elev -2704.95) — transect 53_315deg. Criteria: close=True, flat=True, rising=False. Skipping.*
In this case, it means that for transect ID 53 for angle 315 deg, an exception was applied because no ideal point was found. 

The status of all points is visible in the csv output file (finder_method.csv) in column `status`.

### Status flag available in the Finder module

During the Finder step, MarsCONE detects three characteristic points along each radial transect:
- **bottom** – approximate base of the cone flank,
- **top** – approximate ridge / crater rim,
- **center** – reference point near the cone interior.

For each detected point, the algorithm stores a `status` flag.  
This flag describes **which branch of the detection logic produced the final point** and is intended for Quality Contol, debugging and method comparison (e.g. when inspecting problematic cones).

In general, the workflow is:

1. Try the **main adaptive method** (slope-based and distance-based logic).
2. Optionally **refine** the position around local maxima/minima.
3. If this fails or is ambiguous, fall back to a series of **hierarchical fallbacks**.
4. If no valid candidate can be found, the algorithm may keep the original reference point (e.g. the top) and mark the status as a fallback.

#### How the adaptive slope-based method works in Finder

- **Top detection (`detect_top_by_drop`)**
  - The algorithm analyses the elevation profile between the detected bottom and the geometric centre.
  - It uses `scipy.signal.find_peaks` to locate local maxima that:
    - are high enough relative to the segment (`height` threshold),
    - have sufficient *prominence* (stand out from the surroundings),
    - are wide enough (minimum peak width).
  - Among all valid peaks, the highest one is selected as the **top** and marked with `status = "accepted"`.
  - If no such peak is found, the method falls back to simpler rules
    (e.g. highest point in the segment or in the whole half-profile), with corresponding
    `fallback_*` status codes.

- **Bottom detection (`detect_bottom_adaptive`)**
  - Starting from the detected top, the algorithm looks **outwards** along the profile (away from the cone centre).
  - It smooths the elevation values and computes the **slope** (gradient of elevation with respect to distance).
  - It searches for a zone where:
    - the slope is strongly negative (`slope < -0.05`), i.e. a significant downhill section,
    - and the elevation drop from the top exceeds a minimum threshold (e.g. 0.5 m).
  - From this “drop start”, it follows the profile until:
    - the slope stabilises (near zero) or changes sign, or
    - the slope pattern indicates that the terrain starts rising again.
  - Within this segment it picks the **lowest point** as the bottom candidate.
  - This candidate is accepted (`status = "accepted"`) only if:
    - it is far enough from the top horizontally (at least 10% of the top–centre distance), and
    - it is low enough vertically (at least 5% of the total elevation range of the profile).
  - If these conditions are not satisfied, the method activates a hierarchy of fallbacks
    (`extended_search_lowest`, `fallback_drop_start`, `fallback_segment_lowest`, etc.),
    each of which is explicitly recorded in the `status` column.

In practice, this means that:
- **“accepted”** points are found by the full slope- and distance-based logic and represent
  the most reliable bottoms and tops,
- **`fallback_*`** statuses indicate profiles where the ideal geometric criteria could not be met, and a more permissive rule had to be used instead.

The user may experiment with changing the parameter values in the finder-py/main.py file to better match them to the analysed terrain and cone type.

#### Flag status code summary

| Status                      | Type       | Meaning (short)                                                                 | Typical interpretation / when it occurs                                           |
|-----------------------------|-----------|----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| `accepted`                  | main       | Main adaptive method found a valid bottom that passes all distance checks.      | **Best case** for bottom detection. Use as the primary, high-confidence solution. |
| `refined`                   | refinement | Top refined to a nearby local maximum around the regression-based estimate.     | Top detected robustly and then adjusted to the nearest clear summit candidate.    |
| `refined_alt`               | refinement | Alternative refinement of the top using an additional local maximum criterion.  | Used when the primary refinement is ambiguous; still a **good-quality** top.      |
| `extended_search_lowest`    | fallback   | Bottom chosen as the **lowest point** found in an extended search window.       | Main window did not produce a valid bottom; search extended farther from the top. |
| `fallback_drop_start`       | fallback   | Bottom at the **first significant drop** below the top along the flank.         | Used when a clear minimum is missing, but a strong downward trend is present.     |
| `fallback_lowest`           | fallback   | Bottom as the **lowest point** between the top and the outer boundary.          | Direct “take the lowest point” fallback within the main segment.                  |
| `fallback_segment_lowest`   | fallback   | Bottom as the lowest point in the **entire segment** when other checks fail.    | Last-resort bottom; use with care, may be influenced by local noise/outliers.     |
| `fallback_highest_in_segment` | fallback | Top as the **highest point** within the analysed summit segment.                | Used when prominence/prominence-based criteria are inconclusive.                  |
| `fallback_overall_highest`  | fallback   | Top as the **highest point on the whole side** in the search direction.         | Very robust, but may be more sensitive to DEM artefacts or external peaks.        |
| `fallback_segment_empty`    | fallback   | Top chosen from a global maximum because the local segment is too short/empty.  | Geometry or masking left too few points; top is still usable but less constrained.|
| `fallback_no_top`           | fallback   | No point above the slope threshold; top reconstructed using simple heuristics.  | Indicates profiles with very weak relief or noisy slopes.                         |
| `fallback_side_start`       | fallback   | Top placed near the **edge of the segment** (start of the side).                | Used when no clear summit is found near the centre, but elevation decreases away. |

**Practical use:**

- For most quantitative analyses, points with `status` in `{"accepted", "refined", "refined_alt"}` can be treated as **high-quality detections**.
- Fallback statuses are still useful, but they:
  - often indicate **less ideal geometry**, or  
  - mark profiles where the algorithm had to relax one or more assumptions.
- When validating the method or inspecting outliers, it is recommended to:
  - filter or flag profiles dominated by harsh fallbacks such as  
    `fallback_segment_lowest`, `fallback_overall_highest`, `fallback_segment_empty`,  
  - and visually check a sample of transects for each status category.

**Where to find status:**
The status for each point is available in the `status` column in the finder_methods csv file, as well as in the attribute table in the gpkg files. 


## 8. Module 3 – Analyzer

```bash
analyzer-py/main.py
```

### 8.1. Function

Analyzer aggregates Finder detections and profile data into cone-scale statistics and geometry:
- Base/crater widths/height/dept/volume/slopes and base/crater ratio, base/height ratio.  
- crater center locations:
    - from top points only
    - optionally hybrid centers combining top-based center (70%) with expert input points (30%)

### 8.2. Inputs

Configured in analyzer-py/config.json:
- paths.base – same dataset root
- paths.input.profiles – profile CSVs from Generator (default output/generator/profiles/whole)
- paths.input.points – folder with Finder’s CSV (default output/finder)
- Analyzer expects a file named finder_method.csv inside this folder
- paths.input.centers – optional expert center file folder (*.shp / *.gpkg)
- paths.output.csv – main Analyzer results CSV (default output/analyzer/results.csv)
- paths.output.shapes – folder for vector outputs (buffers, centers, etc.)
- paths.db – GeoPackage database (db/database.gpkg)
- csv.sep – CSV separator (default ";")
- shape.crs – CRS string (same as Generator)

### 8.3. Per-transect metrics

Analyzer typically:
1.	Joins profile information with Finder points by transect_id and cone_id.
2.	For each transect, identifies:
    - all bottom points (types containing "bottom")
    - all top points (types containing "top")
    - center point (type == "C")
3.	Computes metrics such as:
    - height = mean(top_elev) - mean(bottom_elev)
    - bottom_width and top_width (distance between extremal points of each type)
    - center_elev, center_x, center_y
    - center_to_top_diff and others
    - simple shape class (flat, convex, concave) using shape_threshold

These metrics are then written to the file defined by paths.output.csv (or an additional per-transect CSV, depending on the code version).

### 8.4. Per-cone metrics

For each cone_id, Analyzer aggregates per-transect metrics to compute:
- mean height, bottom_width, top_width
- mean top_elev, bottom_elev, center_elev
- descriptors such as center_to_top_diff
- H/W ratios and other derived indices

Using all bottom and top points for the cone, it can compute:
- base ellipse (from bottom points) – major/minor diameters, area, orientation
- crater ellipse (from top points) – crater width and orientation
- approximate volume based on cone geometry
- average side slopes

Results are appended/merged into the main CSV defined by paths.output.csv.

### 8.5. Cone footprints and centers

Based on buffer_distance and aggregated metrics, Analyzer:
- creates buffers around cone centers and writes them as vector layers to paths.output.shapes
- computes crater centers from top points and exports them as GPKG/GeoJSON
- if an expert center file is present in paths.input.centers, it can compute hybrid centers:
    - merges top-based center with expert point 
    - writes a separate layer with hybrid centers

If export_geojson is true, additional GeoJSON files are written for quick visualization.

### 8.6. Running Analyzer

From the repository root:
``` bash
conda activate marscone
python analyzer-py/main.py
```

Example console output:
```bash
✔ Reading profile points and detected features
Analyzing profiles: 100%|████████████████████████| 464/464 [00:01<00:00, 299.42it/s]
✔ Exported 464 measurements to ../data/test_set/output/analyzer/results.csv
✔ Calculating advanced morphometric parameters for each cone...
Analyzing cone geometry: 100%|█████████████████████| 58/58 [00:00<00:00, 726.16it/s]
✔ Exported aggregated results to ../data/test_set/output/analyzer/cone_summary.csv
✔ Generating GeoJSON buffers for cones by shape
✔ Saved: ../data/test_set/output/analyzer/shapes/concave_cones.gpkg
✔ Computing crater centers using top points and least squares
✔ Saved center points to ../data/test_set/output/analyzer/shapes/centers.gpkg
✔ Reading expert crater center points from input/centers
✔ Saved input center points to ../data/test_set/output/analyzer/shapes/centers_input.gpkg
✔ Computing hybrid crater centers (top + expert point)
✔ Saved hybrid center points to ../data/test_set/output/analyzer/shapes/centers_hybrid.gpkg
✔ Updated cone_summary.csv with hybrid coordinates
✔ Exporting unified GeoPackage with cleaned points and fitted ellipses
✔ Saved per-transect bottom points to layer 'points_bottom_axis'
✔ Saved unified GeoPackage to ../data/test_set/output/analyzer/marscone.gpkg
```
If an expert centers file is found in paths.input.centers, you may additionally see logs about hybrid center computation.

## 9. Example outputs
### 9.1. GIS view of MarsCONE results

After running all three modules (Generator → Finder → Analyzer), the results can be inspected directly in a GIS (e.g. QGIS, ArcGIS) using the GeoPackage specified in the configs (typically `db/database.gpkg`) and the output layers created by Analyzer (`output/analyzer/marscone.gpkg`).

A possible view of the final outputs looks like this:

![MarsCONE cone system in QGIS](https://c5studio.pl/marscone/marscone-qgis.webp)

Key layers:
- **`database — transects`** – radial transects generated by the Generator  
- **`database — profiles`** – profile geometries / vertices along each transect  
- **`database — points`** – bottom / top / center points detected by the Finder on each transects
- **`database — temp_cones_buffer`** – buffer size defined in the Generator

- **`marscone — points_top`, `marscone — points_bottom`** – cleaned sets of top/bottom points 
- **`centers-hybrid`** – hybrid centre point (weighted average of expert and automatically determined points) – file available in `output/analyser/shapes/centers_hybrid.gpkg` 

*optionally*
- **`marscone — points_bottom_near_and_far`** - all detected bottom points (near and far) - the best solution is to display the layer according to the unique value with the type () parameter. Most often, E_bottom and N_bottom are nearest points, and S_bottom and W_bottom are farther points.
- **`centers-input`** – centre point (automatically detected points - lowest points between top) – file available in `output/analyser/shapes/centers_input.gpkg` 
- **`centers`** – default points created in input folder – file available in `output/analyser/shapes/centers.gpkg` 
- **`marscone — ellipse_base`** - fitted bottom ellipses created by the Analyzer
- **`marscone — ellipse_top`** - fitted top ellipses created by the Analyzer


These layers allow you to verify the quality of automatic detection and visually inspect cone geometry.

---

#### 9.1.1. How to reproduce this figure in QGIS

To recreate the QGIS view shown above:

1. **Open the GeoPackage**
   - In QGIS: *Layer → Add Layer → Add Vector Layer…*  
   - Select `db/database.gpkg` and load all layers, or at least:
     - `transects`
   - Select `output/analyzer/marscone.gpkg` and load all layers
   - Select `output/analyser/shapes/centers_hybrid.gpkg` and load layers

2. **Add the DEM**
   - Add the DEM used in MarsCONE (e.g. `DTEEC_043987_1825_035521_1825_A01.tif`) as a raster layer.
   - Optional: apply a hillshade or relief style to enhance topography.

3. **Set layer order and preferred style**


### 9.2. `cone_summary.csv` – cone-scale metrics

The main numeric summary produced by the Analyzer is stored in `output/analyzer/cone_summary.csv`.  
Each row corresponds to one cone and contains the following columns:

- **`cone_id`**  
  Unique identifier of the cone.

- **`height`** [m]  
  Cone height: difference between mean top elevation and mean bottom elevation  
  (`height = top_elev − bottom_elev`).

- **`bottom_width`** [m]  
  Effective base diameter derived from the most distal bottom points with respect to the cone centre  
  (not necessarily identical to `base_major_diameter`, which comes from ellipse fitting).

- **`top_elev`** [m]  
  Mean elevation of all detected top points for the cone.

- **`bottom_elev`** [m]  
  Mean elevation of all detected bottom points for the cone.

- **`center_elev`** [m]  
  Mean elevation of all detected center points (`C`) along transects.

- **`center_to_top_diff`** [m]  
  Difference between mean top elevation and mean center elevation  
  (`center_to_top_diff = top_elev − center_elev`).

- **`center_x`**, **`center_y`** [map units]  
  Mean planimetric coordinates of center points (`C`) for the cone, in the project CRS (same CRS as defined in the config, e.g. Mars equirectangular).

- **`shape`**  
  Simple shape class of the cone, based on transect-level metrics and `shape_threshold`, e.g.:  
  `concave`, `convex`, `flat`.

- **`base_area`** [m²]  
  Area of the fitted base ellipse (using bottom points).

- **`base_major_diameter`** [m]  
  Length of the major axis of the fitted base ellipse.

- **`base_minor_diameter`** [m]  
  Length of the minor axis of the fitted base ellipse.

- **`base_center_x`**, **`base_center_y`** [map units]  
  Center coordinates of the fitted base ellipse.

- **`base_angle_deg`** [°]  
  Orientation of the major axis of the base ellipse, measured in degrees (azimuth in the CRS coordinate system).

- **`top_major_diameter`** [m]  
  Length of the major axis of the fitted crater (top) ellipse.

- **`top_minor_diameter`** [m]  
  Length of the minor axis of the fitted crater (top) ellipse.

- **`top_center_x`**, **`top_center_y`** [map units]  
  Center coordinates of the fitted crater (top) ellipse.

- **`top_angle_deg`** [°]  
  Orientation of the major axis of the top ellipse (crater), in degrees.

- **`volume`** [m³]  
  Approximate cone volume estimated from the base geometry and height  
  (frustum-like approximation using base and crater radii).

- **`base_ellipticity`** [-]  
  Dimensionless ellipticity of the base ellipse, typically defined as  
  `1 − (base_minor_diameter / base_major_diameter)`;  
  values close to 0 indicate nearly circular bases, higher values indicate stronger elongation.

- **`elongation_azimuth`** [°]  
  Azimuth of base elongation (orientation of the long axis of the base), derived from the ellipse fit.  
  For symmetric cones this will be similar to `base_angle_deg`.

- **`avg_slope_deg`** [°]  
  Mean side slope angle of the cone, averaged over all transects (degrees).

- **`H_WCO_ratio`** [-]  
  Height-to-base ratio: `H / WCO`, where `H` is `height` and `WCO` is the base width  
  (typically `base_major_diameter`). Indicates relative steepness of the cone.

- **`WCR_WCO_ratio`** [-]  
  Crater-to-base width ratio: `WCR / WCO`, where `WCR` is crater width  
  (derived from the top ellipse) and `WCO` is base width. Values near 0 indicate small craters  
  relative to the cone base, values near 1 indicate very wide craters.

- **`center_lowest_elev`** [m]  
  Lowest elevation among all center points (`C`) for the cone, representing the  
  minimum crater-floor level detected along transects.

- **`depth`** [m]  
  Crater depth with respect to the highest top elevation:  
  `depth = top_elev − center_lowest_elev`.

- **`hybrid_x`**, **`hybrid_y`** [map units]  
  Hybrid crater center coordinates, combining the center estimated from top points  
  with the expert input point (if provided in `input/points`), using a weighted average (70% calculated center and 30% input center).  
  If no expert file is available, these may be identical to the top-based center or left empty,  
  depending on the configuration.


This table can be directly used for statistical analysis, plotting (e.g. height vs. base diameter), or comparison with manually measured cone morphometry.

## 10. Cross-section notebook (`cross-section.ipynb`)
In addition to the CLI workflow, MarsCONE provides an optional Jupyter notebook
(`cross-section.ipynb`) that can be used to generate **publication-ready
files** for individual cones. 

![MarsCONE cone system in QGIS](https://c5studio.pl/marscone/cone18_axis0.svg)

The notebook:

1. Reads the DEM-based profiles from `output/generator/profiles/whole/`.
2. Reads detected points from `output/finder/finder_method.csv`.
3. Reads cone-scale metrics from `output/analyzer/cone_summary.csv`.
4. Lets you select:
   - a particular `cone_id`, and  
   - one **axis** (pair of opposite transects), e.g. `90°/270°` or `0°/180°`.
5. Builds a single **composite cross-section** along this axis, merging:
   - left and right sides of the cone,
   - near and far `bottom` points,
   - `top` points on both sides,
   - the `center` point.


#### Parameters shown in the cross-section plots

For each selected cone and axis, the notebook computes and annotates:

- **`Wco`** – **basal width** along the axis  
  Horizontal distance between the two *near* bottom points on opposite sides of the cone.
- **`Wcr`** – **crater width** along the axis  
  Horizontal distance between the two top points on opposite sides of the cone.

- **`H_left`**, **`H_right`** – **cone heights** for the left and right side  
  Vertical distance between the top and the *near* bottom point on each side, e.g.  
  `H_left = z_top_left − z_bottom_left_near`.

- **`D_left`**, **`D_right`** – **crater depths** along each side  
  Vertical distance between the top and the crater centre, e.g.  
  `D_left = z_top_left − z_center`,  
  where `z_center` is the elevation of the centre point on that axis.

![MarsCONE cone system in QGIS](https://c5studio.pl/marscone/marscone-calculation.png)


## 11. Troubleshooting
- GDAL / PROJ errors<br/>
        Make sure you are using the marscone Conda environment created from marscone_env.yml.<br/>
        On some systems you may need to set PROJ_LIB and GDAL_DATA manually.
- Generator produces no profiles<br/>
	    Check generator-py/config.json paths (paths.base, paths.input.*)<br/>
	    Make sure masks or points exist and the CRS matches the DEM (crs entry)
- Finder finds no points<br/>
	    Ensure that Generator populated the profiles layer in db/database.gpkg<br/>
	    Verify that db_layers.profiles in Finder config matches the actual layer name
- Analyzer cannot find Finder results<br/>
	    Confirm that paths.input.points in Analyzer points to the folder with finder_method.csv<br/>
	    Check that csv.sep matches the separator used by Finder (usually ";")
- No hybrid centers are produced<br/>
	    Ensure that a *.shp or *.gpkg with expert centers is placed in paths.input.centers<br/>
	    Ensure the file contains a cone_id field compatible with the IDs used in the pipeline

## 12. Citation
Śledziowski, J., Pieterek, B., & Jones, T. J. (2025). MarsCONE: A toolbox for automatic detection of Martian pitted cones morphology (1.0.0). Zenodo. https://doi.org/10.5281/zenodo.17887603


