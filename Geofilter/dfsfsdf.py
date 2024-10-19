import geopandas as gpd
from shapely.geometry import Point, MultiPolygon, Polygon
import pycountry

def get_country_code_from_coordinates(lon, lat, world_shapefile_path):
    # Nutzer-Shapefile laden
    # gdf = gpd.read_file(user_shapefile_path)

    # Erstellen des Punktes mit den angegebenen Koordinaten
    point = Point(lon, lat)

    # World-Shapefile laden
    world_gdf = gpd.read_file(world_shapefile_path)
    
    # Iteration durch die Länder und Überprüfung, in welchem Land sich der Punkt befindet
    for country in world_gdf.itertuples():
        geom = country.geometry
        country_name = getattr(country, 'NAME', None)  # Spaltenname anpassen, falls nötig
        
        # Multi-Polygone aufteilen und prüfen
        if isinstance(geom, MultiPolygon):
            for polygon in geom.geoms:
                if polygon.contains(point):
                    country_data = pycountry.countries.get(name=country_name)
                    if country_data:
                        print(f"Punkt liegt in {country_name} (MultiPolygon)")
                        return country_data.alpha_2
                else:
                    print(f"Punkt liegt NICHT in {country_name} (MultiPolygon)")
        elif isinstance(geom, Polygon):  # Für den Fall, dass es ein einzelnes Polygon ist
            if geom.contains(point):
                country_data = pycountry.countries.get(name=country_name)
                if country_data:
                    print(f"Punkt liegt in {country_name} (Polygon)")
                    return country_data.alpha_2
    return None

# Beispielhafte Nutzung der Funktion:
lon = 9.52462  # Beispiel: Längengrad für Wien
lat = 49.54661  # Beispiel: Breitengrad für Wien
world_shapefile_path = 'ne_110m_admin_0_countries.shp'

country_code = get_country_code_from_coordinates(lon, lat, world_shapefile_path)
print(f"Das Länderkürzel ist: {country_code}")
