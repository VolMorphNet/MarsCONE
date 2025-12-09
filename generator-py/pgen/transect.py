import math
from shapely.geometry import LineString
import geopandas as gpd
from os.path import join

GREEN = "\033[92m"

def generate_transects(config):
    base = config["paths"]["base"]
    db_path = join(base, config["paths"]["db"])
    crs = config["crs"]
    length = config["parameters"]["transect_length"]
    angle_step = config["parameters"].get("transect_angle_step", 90)  # default 2 lines (90°)

    mode = config.get("mode", "masks")  # 'masks' or 'points'

    layer_name = config["db_layers"]["points"] if mode == "points" else config["db_layers"]["masks"]
    transects_layer = config["db_layers"]["transects"]

    gdf = gpd.read_file(db_path, layer=layer_name).to_crs(crs)

    transects = []
    num_directions = int(360 / angle_step)
    half_len = length / 2.0

    for idx, row in gdf.iterrows():
        if "Id" in row: # ArcGIS often uses 'Id'
            base_id = row["Id"]
            print(f"Selected ID from ArcGIS: {base_id}")
        elif "id" in row: # Lowercase 'id'
            base_id = row["id"]
        elif "FID" in row: # File Geodatabase / Shapefile FID
            base_id = row["FID"]
        elif "OBJECTID" in row: # Enterprise Geodatabase / Feature Classes
            base_id = row["OBJECTID"]
        else:
            # Fallback if no specific ID column is found
            base_id = idx + 1 # Fallback to DataFrame index + 1
            print(f"No recognised ID column for row {idx}. Selected {base_id}.")
        geom = row.geometry

        if mode == "masks":
            centroids = [geom.centroid]
        elif geom.geom_type == "Point":
            centroids = [geom]
        elif geom.geom_type == "MultiPoint":
            centroids = list(geom.geoms)
        else:
            raise ValueError(f"Unsupported geometry type: {geom.geom_type}")

        for i, centroid in enumerate(centroids):
            cone_id = f"{base_id}_{i+1}" if len(centroids) > 1 else base_id

            for j in range(num_directions):
                angle_deg = j * angle_step
                angle_rad = math.radians(angle_deg)

                dx = half_len * math.cos(angle_rad)
                dy = half_len * math.sin(angle_rad)

                p1 = (centroid.x - dx, centroid.y - dy)
                p2 = (centroid.x + dx, centroid.y + dy)
                line = LineString([p1, p2])

                transects.append({
                    "id": f"{cone_id}_{int(angle_deg)}deg",
                    "cone_id": cone_id,
                    "orientation": f"{int(angle_deg)}deg",
                    "geometry": line
                })

    transects_gdf = gpd.GeoDataFrame(transects, crs=crs)
    transects_gdf.to_file(db_path, layer=transects_layer, driver="GPKG")

    print(f"✔ {GREEN}Saved {len(transects)} transects (every {angle_step}°) to layer '{transects_layer}' in {db_path}")
