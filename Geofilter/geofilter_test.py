#---------------------------------------------------------------------------------------------------------------
# Autor: Elija Gschnitzer
# Datum: Mai 2024
# Beschreibung: Programm zum Aufteilen von Potentialen in Nuts3-Ebenen auf Netzknoten in diesen Ebenen.
#---------------------------------------------------------------------------------------------------------------

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import matplotlib.pyplot as plt

# Datentyp der Ausgabedatei wählen: x=0 für xlsx, x=1 für csv (xlsx empfohlen!)
x = 0     
# Shapefile erstellen? ja oder nein
z = 'ja'

# Einlesen des shapefiles der Nuts3-Ebene     
nuts3 = gpd.read_file('STATISTIK_AUSTRIA_NUTS3_20230101.shp', encoding='utf-8')
nuts3 = nuts3.to_crs(epsg=4326)     # Koordinatenbezugssystems auf WGS84 ändern


#print(nuts3.head())  # Zeigt die ersten 5 Zeilen des GeoDataFrames an
#print(nuts3.columns)  # Zeigt alle Spaltennamen an
#print(nuts3.info())  # Gibt Informationen über die Datenstruktur aus

selected_columns = ['g_id', 'g_name', 'geometry']  # Beispielspalten
nuts3 = nuts3[selected_columns]

styled_df = nuts3.style.format(precision=4)

#print(nuts3['geometry'])
geometry = dict(nuts3['geometry'])

for geo in geometry:
    print(str(geo[2]) + '\n')


nuts3.plot(column='g_id', cmap='OrRd', legend=True, figsize=(10, 8))
plt.title('NUTS3 Regionen')
plt.show()

# Einlesen der Windpotentiale
WP_data = pd.read_excel('Windpotential.xlsx')

# Verküpfen der Daten basierend auf einem gemeinsamen Schlüssel 
nuts3_WP_data = nuts3.merge(WP_data, how='left', left_on='g_id', right_on='ID')  

# Speichern des aktualisierten Shapefiles
nuts3_WP_data.to_file('nuts3_mit_WP.shp', encoding='utf-8')

#---------------------------------------------------------------------------------------------------------------
# Erzeugen eines Shapefiles aus dem Knotenfile

# Einlesen der Knoten-Tabelle
knoten_df = pd.read_excel('tbl_Stamm_Knoten_STARTNETZ_380_220_110_20.xlsx')

# Funktion, um Ziffern vor Kommastelle und die ersten 3 Nachkommastellen einer Zahl zu extrahieren
def extrahiere_ziffern(zahl):
    ganzzahliger_teil, dezimalteil = str(zahl).split('.')    # Aufteilen der Zahl in den ganzzahligen und den Dezimalteil
    dezimalteil = dezimalteil[:3]                            # Nur die ersten 3 Ziffern nach dem Komma behalten
    formatierte_zahl = f"{ganzzahliger_teil}.{dezimalteil}"
    return formatierte_zahl

# Funktion, um einen String aus den Ziffern von Breiten- und Längengrad zu erzeugen
def erzeuge_koordinaten_string(lat, lon):
    lat_str = extrahiere_ziffern(lat)
    lon_str = extrahiere_ziffern(lon)
    return f"{lat_str},{lon_str}"

# Neue Spalte 'latlon' erstellen und füllen
knoten_df['latlon'] = knoten_df.apply(lambda row: erzeuge_koordinaten_string(row['lat'], row['lon']), axis=1)

zeilen_zu_loeschen = []
# Iteriere über alle eindeutigen Werte in 'latlon' und behalte nur den Knoten mit dem kleinsten Wert
for koordinate in knoten_df['latlon'].unique():
    subset = knoten_df[knoten_df['latlon'] == koordinate]
    kleinster_wert = subset['SpgsebeneWert'].min()
    kleinster_wert_index = subset[subset['SpgsebeneWert'] == kleinster_wert].index
    zeilen_zu_loeschen.extend(subset.index.difference(kleinster_wert_index))

# Lösche die Zeilen mit mehrfachen Knoten am selben Ort aus dem ursprünglichen DataFrame
knoten_df.drop(zeilen_zu_loeschen, inplace=True)

# Entferne die Spalte 'latlon', da sie nicht mehr benötigt wird
knoten_df.drop(columns=['latlon'], inplace=True)

# Knoten entfernen, welche sich nicht in Österreich befinden 
zeilen_zu_loeschen2 = []
for index, row in knoten_df.iterrows():   
    if row['Land'] != 'AT':
        zeilen_zu_loeschen2.append(index)

if zeilen_zu_loeschen2:
    print("Es wurden Knoten aus der Tabelle entfernt, die sich nicht in Österreich befinden.")

knoten_df.drop(zeilen_zu_loeschen2, axis=0, inplace=True)

# Erstellen einer Geometrie-Spalte basierend auf den Breiten- und Längengraden
geometry = [Point(xy) for xy in zip(knoten_df['lon'], knoten_df['lat'])]

# Erstellen eines GeoDataFrames
gdf = gpd.GeoDataFrame(knoten_df, geometry=geometry)

# Setzen des Koordinatenbezugssystems (CRS) auf WGS84 (EPSG:4326)
gdf.crs = {'init': 'epsg:4326'}

# Speichern des Shapefiles
output_shapefile = 'Knoten.shp'
gdf.to_file(output_shapefile, driver='ESRI Shapefile')

#---------------------------------------------------------------------------------------------------------------
# Knoten den Nuts3-Ebenen zuweisen

geodf1 = gpd.read_file('nuts3_mit_WP.shp')
geodf2 = gpd.read_file('Knoten.shp')
geodf_join = geodf2.sjoin(geodf1,how="left")    

#---------------------------------------------------------------------------------------------------------------
# Potential auf Knoten in Ebene aufteilen

# Neue Spalte für das aufgeteilte Potential erstellen
geodf_join['End_Pot'] = 0.0

# Durchläuft jede Zeile des shapefiles
for index, row in geodf_join.iterrows():
    id = row['ID']  
    pot_spalte = 'Rest_Pot'  
    rest_pot = row[pot_spalte]      # Wert aus der Spalte erhalten
    anzahl_id = geodf_join['ID'].value_counts().get(id, 0)  # Anzahl der gleichen ID zählen
    if anzahl_id > 0:
        geodf_join.at[index, 'End_Pot'] = rest_pot / anzahl_id  # Berechnetes Pot in neue Spalte einfügen

# Nachkommastellen auf 2 runden
geodf_join['End_Pot'] = geodf_join['End_Pot'].astype(float).round(2) 

# Entfernen von doppelt vorkommenden Spalten 
geodf_join = geodf_join.drop(columns=['g_id'])
geodf_join = geodf_join.drop(columns=['g_name'])

# Hinweis ausgeben, wenn sich in Ebene kein Knoten befindet
vergleich = ~WP_data['ID'].isin(geodf_join['ID'])
if vergleich.any():
    nicht_gefunden = WP_data[vergleich][['ID','Name']]
    print("In diesen NUTS3-Ebenen befindet sich kein Knoten:")
    print(nicht_gefunden)

#---------------------------------------------------------------------------------------------------------------
# Ergebnis
if x == 0:
    geodf_join.to_excel('output.xlsx', index=False)
elif x == 1:  
    geodf_join.to_csv('output.csv', index=False)  
else:
    print("Ungültige Wahl der output-Datei")

# Als Shapefile speichern 
if z == 'ja':
    output_shp = 'output.shp'                                
    geodf_join.to_file(output_shp, driver='ESRI Shapefile')
