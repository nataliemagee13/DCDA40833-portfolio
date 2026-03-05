from pathlib import Path
from typing import Optional, Tuple

import folium
import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import ArcGIS, Nominatim


def _detect_coordinate_columns(data: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """Find likely latitude/longitude column names in the CSV."""
    lat_candidates = ["Latitude", "latitude", "lat", "Lat", "LAT"]
    lon_candidates = ["Longitude", "longitude", "lon", "lng", "Long", "LON", "LNG"]

    lat_col = next((col for col in lat_candidates if col in data.columns), None)
    lon_col = next((col for col in lon_candidates if col in data.columns), None)
    return lat_col, lon_col


def _geocode_addresses(data: pd.DataFrame) -> pd.DataFrame:
    """Geocode address strings into Latitude/Longitude columns."""
    if "Address" not in data.columns:
        raise KeyError("CSV must include either Latitude/Longitude or Address columns")

    nominatim = Nominatim(user_agent="dcda40833-hometown-map")
    arcgis = ArcGIS(timeout=10)

    nominatim_geocode = RateLimiter(nominatim.geocode, min_delay_seconds=1)
    arcgis_geocode = RateLimiter(arcgis.geocode, min_delay_seconds=0.2)

    lats: list = []
    lons: list = []

    print("No Latitude/Longitude columns found. Geocoding addresses...")
    for index, row in data.iterrows():
        name = str(row.get("Name", f"Row {index + 1}"))
        address = str(row.get("Address", "")).strip()

        if not address:
            print(f"WARNING: Missing address for '{name}'")
            lats.append(None)
            lons.append(None)
            continue

        print(f"Geocoding {index + 1}/{len(data)}: {name}")

        # Try a few query formats for better match accuracy.
        queries = []
        for query in [
            address,
            f"{address}, Fort Worth, TX",
            f"{name}, {address}",
            f"{name}, Fort Worth, TX",
        ]:
            if query not in queries:
                queries.append(query)

        location = None
        matched_query = None
        matched_source = None

        for query in queries:
            location = nominatim_geocode(query)
            if location is not None:
                matched_query = query
                matched_source = "Nominatim"
                break

        if location is None:
            for query in queries:
                location = arcgis_geocode(query)
                if location is not None:
                    matched_query = query
                    matched_source = "ArcGIS"
                    break

        if location is None:
            print(f"WARNING: Could not geocode '{name}' -> {address}")
            lats.append(None)
            lons.append(None)
            continue

        print(
            f"Matched '{name}' with {matched_source} using query: {matched_query}"
        )

        lats.append(float(location.latitude))
        lons.append(float(location.longitude))

    geocoded = data.copy()
    geocoded["Latitude"] = lats
    geocoded["Longitude"] = lons
    return geocoded


def main() -> None:
    csv_name = "hometown_locations.csv"
    html_name = "hometown_map.html"

    cwd = Path.cwd()
    script_dir = Path(__file__).resolve().parent

    print("=== Hometown Map Debug ===")
    print(f"Current working directory: {cwd}")
    print(f"Script directory: {script_dir}")

    csv_path = cwd / csv_name
    if not csv_path.exists():
        print(f"ERROR: CSV not found in current directory: {csv_path}")
        alt_csv_path = script_dir / csv_name
        if alt_csv_path.exists():
            print(f"Found CSV in script directory instead: {alt_csv_path}")
            csv_path = alt_csv_path
        else:
            raise FileNotFoundError(
                f"Could not find '{csv_name}' in '{cwd}' or '{script_dir}'"
            )

    print(f"Loading CSV from: {csv_path}")
    data = pd.read_csv(csv_path)
    print(f"CSV loaded successfully. Rows: {len(data)}")
    print(f"CSV columns: {list(data.columns)}")

    if "Name" not in data.columns:
        raise KeyError("CSV is missing the required 'Name' column")

    lat_col, lon_col = _detect_coordinate_columns(data)
    if lat_col and lon_col:
        print(f"Using coordinate columns: {lat_col}, {lon_col}")
        data = data.copy()
        data["Latitude"] = pd.to_numeric(data[lat_col], errors="coerce")
        data["Longitude"] = pd.to_numeric(data[lon_col], errors="coerce")
    else:
        data = _geocode_addresses(data)

    plotted = data.dropna(subset=["Latitude", "Longitude"]).copy()
    if plotted.empty:
        raise ValueError("No valid coordinates available to plot on the map")

    print(f"Locations with valid coordinates: {len(plotted)}")

    map_center = [plotted["Latitude"].mean(), plotted["Longitude"].mean()]
    print(f"Map center: {map_center[0]:.6f}, {map_center[1]:.6f}")

    hometown_map = folium.Map(location=map_center, zoom_start=12, tiles=None)

    folium.TileLayer(
        tiles="https://api.mapbox.com/styles/v1/nataliemagee/cmmdqv4dd001901s251khd3i9/tiles/256/{z}/{x}/{y}@2x?access_token=pk.eyJ1IjoibmF0YWxpZW1hZ2VlIiwiYSI6ImNtbTB2YzgyNzAyemYycW9jaHE0aGxqeDkifQ.x_Y61VqJTIeQkFoYbYQzWA",
        attr="Mapbox",
        name="Natalie's Custom Map",
    ).add_to(hometown_map)

    for _, row in plotted.iterrows():
        popup_lines = [f"<strong>{row['Name']}</strong>"]
        if "Type" in row and pd.notna(row["Type"]):
            popup_lines.append(f"Type: {row['Type']}")
        if "Address" in row and pd.notna(row["Address"]):
            popup_lines.append(str(row["Address"]))

        folium.Marker(
            location=[float(row["Latitude"]), float(row["Longitude"])],
            popup="<br>".join(popup_lines),
        ).add_to(hometown_map)

    html_path = cwd / html_name
    hometown_map.save(str(html_path))

    print(f"Map saved to: {html_path}")
    print(f"File exists after save: {html_path.exists()}")
    print("Map created!")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        raise