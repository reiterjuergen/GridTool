# Initialization
import time
import matplotlib.pyplot as plt
import math
import numpy as np
import json
import tkinter as tk
from tkinter import filedialog
from tkinter import simpledialog
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, MultiPolygon, Polygon
import pycountry
import os
import configparser
import xlsxwriter

# Start overall runtime timer
overallruntime_start = time.time()

# Set neighbourhood threshold radius to determine, how close endnodes have 
# to be together to get grouped
neighbourhood_threshold = 0.5

# Max. length of a line which can be a type 'busbar', in km
busbar_max_length = 1

# Multiplier factor for the exported length of line (slack compensation)
way_length_multiplier = 1.2

# Display all numbers (up to 15 digits) in console without scientific notation
np.set_printoptions(precision=15, suppress=True)

# In the settings, various options for calculation and visualization can be
# turned on or off

class Settings:
    def __init__(self):

        # Calculating real line length?
        # Set if the real line length should be calculated (may take some minutes) or
        # the beeline ("Luftlinie") should be used
        self.calculate_real_line_length = True
        
        # If real line length gets visualized, set threshold to plot only ways which
        # have a difference in beeline-length/real-length of at least x% (standard: 5%)
        self.beeline_visu_treshold_diff_percent = 5.0

        # If real line length gets visualized, set threshold to plot only ways which
        # have a difference in beeline-length/real-length of at least xkm (standard: 0.5km)
        self.beeline_visu_treshold_diff_absolut = 0.5

        # Export the Line and Node data in LEGO format?
        self.lego_export = True

        # Toggle visualizations on/off
        
        # Recommended visualizations
        # Visualize all selected ways, hence the original dataset
        self.plot_ways_original = True

        # Visualize all selected ways, while they are being grouped. This plot
        # includes the original and the new ways, including the threshold-circles
        self.plot_ways_grouping = False

        # Visualize all selected ways on map, final dataset with endnodes grouped
        self.plot_ways_final = True

        # Visualize distances between all endnodes to easier set neighbourhood_threshold
        self.histogram_distances_between_endpoints = False

        # Visualize Comparison between real line course and beeline
        self.plot_comparison_real_beeline = True
        
        # Optional visualizations, for debugging purposes and in-depth-research
        # Visualize length of busbars to set busbar_max_length
        self.histogram_length_busbars = False

        # Visualize how many endnodes are stacked on top of each other
        self.histogram_stacked_endnodes = False
        
        # Visualize how many neighboring endnodes are grouped together 
        self.histogram_neighbouring_endnodes = False
        
        # Visualize all stacked endnodes on map
        self.plot_stacked_endnodes = False
        
        # Visualize all neighboring endnodes on map
        self.plot_neighbouring_endnodes = False

settings = Settings()

# Print overall runtime
print(f"Overall runtime: {time.time() - overallruntime_start} seconds")

def my_import_json():
    """
    DESCRIPTION
    This function opens a UI to select a *.json file. With the given
    file name and file path the *.json file will be converted to a list
    object. Unnecessary header files, which will be created by overpass,
    will be deleted.

    INPUT
    (none)

    OUTPUT
    data_raw ... all data from the imported *.json file as list
    file_name ... name of file
    file_path ... path of file
    """
    print('Start importing Data (*.json file)...')

    # Open UI to select file
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
    file_name = file_path.split('/')[-1]
    
##    file_path = 'C:/Users/gezz/Documents/Uni/Master/Masterarbeit/GridTool-main/2022-08-02_Austria_220kV_and_380kV.json'
##    file_name = '2022-08-02_Austria_220kV_and_380kV.json'
    
    start_time = time.time()

    # Print file path and filename to console
    print(f'   ... file path: {file_path} \n   ... file name: {file_name}')
            
    # Import and decode selected .json file into workspace with explicit UTF-8 encoding
    with open(file_path, 'r', encoding='utf-8') as f:
        data_raw_jsonimport = json.load(f)
    
    # Strip unnecessary header data from export file, keep relevant elements
    data_raw = data_raw_jsonimport['elements']

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data_raw, file_name, file_path


def my_separate_raw_data_add_UID(data_raw):
    """
    DESCRIPTION
    This function imports the raw data, looks for 'node' and 'way' elements
    and separates them from raw data to save them in separate variables
    with type "list". If the data exported from OSM has corrupted 
    elements (hence, a field like "tags" is missing), this element will be 
    ignored. A manual review of the *.json file will then be necessary.
    A unique identifier number (UID) will be created and added to 
    every way element.

    INPUT
    data_raw ... imported json data as list

    OUTPUT
    data_nodes_all ... all node elements as list
    data_ways_all ... all way elements as list
    """
    start_time = time.time()
    print('Start separating raw data into way- and node-elements... (takes a few seconds)')
    
    # Preallocation of counter variables
    data_nodes_all = []
    data_ways_all = []
    
    # Separate nodes and ways elements from raw data
    for element in data_raw:
        if element['type'] == 'node':
            data_nodes_all.append(element)
        elif element['type'] == 'way':
            data_ways_all.append(element)
    
    # Create unique ID (UID) and add it
    for i, way_element in enumerate(data_ways_all):
        way_element['UID'] = i + 1

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data_nodes_all, data_ways_all

def my_add_coordinates(data, data_nodes_all):
    """
    DESCRIPTION
    The first and last node IDs, hence the endpoints, will be extracted 
    from every way element and the corresponding lon/lat coordinates
    will be added to every way element. Since lon/lat coordinates don't
    give an intuitive feeling of distances in a plot, x/y coordinates in km
    will be calculated. This will be done by a rough (but sufficient)
    approximation: The midpoint (COG - center of gravity) of all lon/lat
    coordinates will be calculated and will be the 0-origin of the x/y plane.
    An approximation formula calculates the km-per-degree-conversion on this 
    point on earth. From every endpoint, the latitudinal/longitudinal distance 
    to the midpoint will be converted to the x/y km distance, this x/y
    value will be added to every way element. Using that information, 
    the distance between the endpoints will be calculated and added too.
    
    INPUT
    data ... dataset of all way elements
    data_nodes_all ... dataset of all node elements
    
    OUTPUT
    data ... the updated dataset of all way elements: IDs of endnodes, 
             lat/lon coordinates, x/y coordinates, length of line
    degrees_to_km_conversion ... the necessary information to convert lon/lat
                                 to x/y coordinates for further use of
                                 grouped endnodes in another function.
    """
    start_time = time.time()
    print('Start adding coordinates to each way... (takes a few seconds)')

    # Create a list of all node ids
    list_all_node_IDs = [node['id'] for node in data_nodes_all]
  
    # Add all endnode coordinates to data
    for way in data:
        # Add first and last endnode IDs as separate elements to data
        way['ID_node1'] = way['nodes'][0]
        way['ID_node2'] = way['nodes'][-1]
        
        # Find the position of the endnode id in list_all_node_IDs
        position_node1 = list_all_node_IDs.index(way['ID_node1'])
        position_node2 = list_all_node_IDs.index(way['ID_node2'])
                              
        # Use this position to assign the lon/lat coordinates to data
        way['lon1'] = data_nodes_all[position_node1]['lon']
        way['lat1'] = data_nodes_all[position_node1]['lat']
        way['lon2'] = data_nodes_all[position_node2]['lon']
        way['lat2'] = data_nodes_all[position_node2]['lat']
    
    # Calculate latitudinal/longitudinal midpoint of all coordinates
    mean_lat = np.mean([way['lat1'] for way in data] + [way['lat2'] for way in data])
    mean_lon = np.mean([way['lon1'] for way in data] + [way['lon2'] for way in data])
    
    # Determine if we are on North/South Hemisphere ...
    if mean_lat > 0:
        print('   INFO: Majority of nodes are on the NORTH and ', end='')
    else:
        print('   INFO: Majority of nodes are on the SOUTH and ', end='')
    
    # ... and East/West Hemisphere, then print this information to console
    if mean_lon > 0:
        print('EASTERN hemisphere')
    else:
        print('WESTERN hemisphere')
    
    print('   ... start calculating and adding x/y coordinates...')
    
    # Approximate km-per-degree conversion at the mean position
    radians = np.deg2rad(mean_lat)
    
    km_per_lon_deg = (111132.954 * np.cos(radians) 
                      - 93.55 * np.cos(3 * radians) 
                      + 0.118 * np.cos(5 * radians)) / 1000
    
    km_per_lat_deg = (111132.92 
                      - 559.82 * np.cos(2 * radians) 
                      + 1.175 * np.cos(4 * radians) 
                      - 0.0023 * np.cos(6 * radians)) / 1000
    
    # Calculate the difference in degrees for each point from midpoint
    delta_lon1 = np.array([way['lon1'] for way in data]) - mean_lon
    delta_lon2 = np.array([way['lon2'] for way in data]) - mean_lon
    delta_lat1 = np.array([way['lat1'] for way in data]) - mean_lat
    delta_lat2 = np.array([way['lat2'] for way in data]) - mean_lat
    
    # Convert the delta_degree into delta_kilometer, as x1/x2/y1/y2
    x1 = delta_lon1 * km_per_lon_deg
    x2 = delta_lon2 * km_per_lon_deg
    y1 = delta_lat1 * km_per_lat_deg
    y2 = delta_lat2 * km_per_lat_deg
    
    # Add x/y coordinates to data
    for i, way in enumerate(data):
        way['x1'] = x1[i]
        way['y1'] = y1[i]
        way['x2'] = x2[i]
        way['y2'] = y2[i]
    
    print('   ... calculate length of each line and add it...')
    
    # Calculate distances between endpoints and add it
    lengths = np.sqrt((x1 - x2)**2 + (y1 - y2)**2)
    for i, way in enumerate(data):
        way['length'] = lengths[i]
    
    # Return the conversion data to use it later again for grouped nodes
    degrees_to_km_conversion = [km_per_lon_deg, km_per_lat_deg, mean_lon, mean_lat]
        
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data, degrees_to_km_conversion, mean_lat, mean_lon

def my_count_voltage_levels(data):
    """
    DESCRIPTION
    This function reads the tag information about the voltage level and 
    adds that information to every way element. If a way has two or three
    different voltage levels, the corresponding way will be
    doubled/tripled automatically. A list of all voltage levels will be
    displayed to the console.

    INPUT
    data ... dataset of all way elements

    OUTPUT
    data ... updated dataset of all way elements: ways with multiple 
             voltage levels got cloned and "number of voltage levels" and
             the voltage level got added to every way element
    voltage_levels_unique ... a list of all voltage levels in the dataset
    """
    start_time = time.time()
    print('Start counting voltage levels...')
    
    for way in data:
        if 'voltage' not in way['tags']:
            # Warn the user if a way element lacks the "voltage" tag
            print(f'   ATTENTION! Way element UID {way["UID"]} does not contain a field "voltage". This way wont be selected.')
            continue

        voltage_levels = []

        # Parse the "voltage" tag into a list of numeric values
        voltage_levels = list(map(float, way['tags']['voltage'].split(';')))
        
        if any(np.isnan(voltage_levels)):
            # Warn the user if a voltage level is invalid or unknown
            print(f'   ATTENTION! UNKNOWN voltage level ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way wont be selected.')
            continue
        
        if len(voltage_levels) == 1:
            # Single voltage level
            way['voltage'] = voltage_levels[0]
            way['vlevels'] = 1
        elif len(voltage_levels) == 2:
            # Two voltage levels require duplication
            way['voltage'] = None
            way['vlevels'] = 2
            print(f'   ATTENTION! Two voltage levels ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way will be duplicated.')
        elif len(voltage_levels) == 3:
            # Three voltage levels require triplication
            way['voltage'] = None
            way['vlevels'] = 3
            print(f'   ATTENTION! Three voltage levels ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way will be tripled.')
        else:
            # Unknown number of voltage levels
            way['voltage'] = None
            way['vlevels'] = None
            print(f'   ATTENTION! Unknown voltage levels ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way wont be selected.')
    
    print('\n   ... start cloning lines with multiple voltage levels... (may take a few seconds)')
    
    num_of_cloned_ways = 0
    iterations_to_skip = 0
    
    i = 0
    while i < len(data):
        if iterations_to_skip > 0:
            # Skip over iterations that were modified in the previous step
            iterations_to_skip -= 1
            i += 1
            continue
        
        if data[i]['vlevels'] == 2:
            # Duplicate ways with two voltage levels
            voltage_levels = list(map(float, data[i]['tags']['voltage'].split(';')))
            way_to_clone_a = data[i].copy()
            way_to_clone_b = data[i].copy()
            way_to_clone_a['voltage'] = voltage_levels[0]
            way_to_clone_b['voltage'] = voltage_levels[1]
            data.insert(i + 1, way_to_clone_b)
            data[i] = way_to_clone_a
            num_of_cloned_ways += 1
            iterations_to_skip = 1
        elif data[i]['vlevels'] == 3:
            # Triplicate ways with three voltage levels
            voltage_levels = list(map(float, data[i]['tags']['voltage'].split(';')))
            way_to_clone_a = data[i].copy()
            way_to_clone_b = data[i].copy()
            way_to_clone_c = data[i].copy()
            way_to_clone_a['voltage'] = voltage_levels[0]
            way_to_clone_b['voltage'] = voltage_levels[1]
            way_to_clone_c['voltage'] = voltage_levels[2]
            data.insert(i + 1, way_to_clone_c)
            data.insert(i + 1, way_to_clone_b)
            data[i] = way_to_clone_a
            num_of_cloned_ways += 2
            iterations_to_skip = 2
        i += 1
    
    # Extract all unique voltage levels and their occurrences
    voltage_levels = [way['voltage'] for way in data if way['voltage'] is not None]
    voltage_levels_unique, voltage_levels_occurance = np.unique(voltage_levels, return_counts=True)
    
    # Sort the voltage levels for better presentation
    voltage_levels_sorted = sorted(zip(voltage_levels_unique, voltage_levels_occurance), key=lambda x: x[0], reverse=True)
    
    print('\n')
    print(f"{'voltage_level':>15} {'number_of_ways':>15}")
    for level, count in voltage_levels_sorted:
        print(f"{level:>15} {count:>15}")
    
    # Display how many ways have unknown voltage levels
    print(f'   ... there are {len(data) - sum(voltage_levels_occurance)} way(s) with unknown voltage level.')
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    
    return data, voltage_levels_unique

def my_ask_voltage_levels(voltage_levels_sorted):
    """
    DESCRIPTION
    This function opens an UI which displays all found voltage
    levels of the dataset. The user can select one / multiple / all
    voltage levels, this information will be returned as a list. If the user
    cancels the dialog, all voltage levels will be selected.

    INPUT
    voltage_levels_sorted ... a list of all unique voltage levels of dataset

    OUTPUT
    voltage_levels_selected ... a list of all selected voltage levels
    """

    # Set up the Tkinter root dialog (hidden)
    root = tk.Tk()
    root.withdraw()

    voltage_levels_str = [str(v) for v in voltage_levels_sorted]

    # Open a dialog for voltage level selection
    voltage_levels_selected_str = simpledialog.askstring("Voltage Level Selection", "Please select one or multiple voltage levels (separated by commas):", initialvalue=", ".join(voltage_levels_str))

    # Parse the selected voltage levels into a list
    if voltage_levels_selected_str:
        voltage_levels_selected = list(map(float, voltage_levels_selected_str.split(',')))
    else:
        voltage_levels_selected = voltage_levels_sorted

    return voltage_levels_selected

def my_select_ways(data_ways_all, vlevels_selected):
    """
    DESCRIPTION
    This function copies all ways, which have a voltage level which got
    selected, to a new list.

    INPUT
    data_ways_all ... dataset of all ways
    vlevels_selected ... list of selected voltage levels

    OUTPUT
    data_ways_selected ... dataset of all ways which have a selected
                           voltage level
    """
    start_time = time.time()
    print('Start selecting ways according to their voltage level...')
    
    # Filter the dataset based on selected voltage levels
    data_ways_selected = [way for way in data_ways_all if way['voltage'] in vlevels_selected]
   
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data_ways_selected


def my_delete_busbars(data, bool_plot, busbar_max_length):
    """
    DESCRIPTION
    This function checks if a way is declared as a busbar or bay, if so, it
    checks if its length is less than the max threshold and adds a flag
    to that way element. The length of a busbar will be saved in a
    separate variable, which can optionally be plotted in a histogram to
    set the max. busbar length accordingly. All busbars will be extracted to 
    a separate variable and then deleted from the original dataset.

    INPUT
    data ... dataset of selected ways
    bool_plot ... settings object for plotting
    busbar_max_length ... the maximum length a busbar can have

    OUTPUT
    data ... updated dataset with all busbars deleted
    data_busbars ... all way elements which are busbars
    """
    
    start_time = time.time()
    print('Start deleting ways with type "busbar" or "bay"...')
    
    # Initialize counter for busbars
    i_busbars_bays = 0
    lengths_of_busbars = []
    
    # go through all way-elements
    for i_ways in range(len(data)):
        # Condition if the tag field "line" exists
        b_line_field_exists = 'line' in data[i_ways]['tags']
        
        # Condition if length of current way is less than max. busbar length
        b_length_ok = data[i_ways]['length'] < busbar_max_length
        
        # if "line" field exists and if its value is "busbar" or "bay"
        if b_line_field_exists and (data[i_ways]['tags']['line'] in ['busbar', 'bay']):
            # and if its length isn't too long
            if b_length_ok:
                # Set flag that current way is a busbar/bay
                data[i_ways]['busbar'] = True 
                
                # Increase counter if found busbars or bays
                i_busbars_bays += 1
                
                # Save its length for an optional histogram
                lengths_of_busbars.append(data[i_ways]['length'])
            else:
                print(f'   ATTENTION! Way Element UID {data[i_ways]["UID"]} has type "busbar" or "bay", but is too long. \n'
                      f'               Length: {data[i_ways]["length"]:.2f} km of max. {busbar_max_length:.1f} km \n'
                      f'               This way won\'t be added to the "busbar" exception list.')
                data[i_ways]['busbar'] = False
        else:
            # If it's not a busbar nor bay...
            data[i_ways]['busbar'] = False
    
    # extract all busbars/bays to a separate variable
    data_busbars = [way for way in data if way['busbar']]
   
    # delete all busbars/bays from original dataset
    data = [way for way in data if not way['busbar']]
    
    # Optional: Histogram of busbar/bays lengths, to set max busbar length
    if bool_plot.histogram_length_busbars:
        plt.figure()
        plt.hist(lengths_of_busbars, bins=200)
        plt.title('Lengths of busbars/bays below busbar-max-length-threshold')
        plt.xlabel('Length [km]')
        plt.ylabel('Number of busbars with that length')
        plt.show()
    
    print(f'   ... {i_busbars_bays} busbars have been deleted\n   ... finished! ({time.time() - start_time:.3f} seconds)')
    
    return data, data_busbars

def my_count_possible_railroad(data):
    """
    DESCRIPTION
    This function checks every way element, if it could potentially be a
    railroad line. The main property this function is looking for is the
    typical railroad frequency of 16,67 Hz. If a line has this frequency
    in its tags, it will be copied to a separate variable for checking.

    INPUT
    data ... the dataset of selected ways

    OUTPUT
    data ... updated dataset, including a flag if a way may be a railroad line
    railroad_candidates ... list of all UIDs which may be a railroad line
    """
    start_time = time.time()
    print('Start detecting lines which could be railroad lines...')
    
    railroad_candidates = []

    for way in data:
        # Initialize the "railroad_candidate" flag
        way['railroad_candidate'] = False
        
        # Check if frequency tag indicates railroad characteristics (16.67 Hz)
        if 'frequency' in way['tags'] and float(way['tags']['frequency']) < 17 and float(way['tags']['frequency']) > 16:
            way['railroad_candidate'] = True
            railroad_candidates.append({'UID': way['UID'], 'voltage_level': way['voltage'], 
                                  'reason': 'tag "frequency" has a value between 16 Hz and 17 Hz'})

    if not railroad_candidates:
        # Handle case where no railroad candidates are found
        railroad_candidates.append({'UID': 'No possible railroad candidate in all ways of those selected voltage levels found!'})
        print('   ... no potentially railroad lines found.')
    else:
        # Count unique railroad candidates
        unique_railroad_candidates = len(set([candidate['UID'] for candidate in railroad_candidates]))
        print(f'   ... {unique_railroad_candidates} ways could potentially be a railroad line.')
        print('   ... Please refer in workspace to variable candidates to manually check them if necessary!')
    
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data, railroad_candidates

def my_count_possible_dc(data):
    """
    DESCRIPTION
    This function checks every way element, if it could potentially be a
    DC line. There are three hints that a line may be a DC line: It has
    only 1 cable, the frequency is "0" or name contains somewhere the two
    letters "dc". If one or more of those checks are correct, the UID,
    reason and voltage level will be copied to a separate variable for
    later manual checks.

    INPUT
    data ... the dataset of selected ways

    OUTPUT
    data ... updated dataset, including a flag if a way may be a DC line
    dc_candidates ... list of all UIDs which may be a DC line
    """
    start_time = time.time()
    print('Start detecting lines which could be DC lines...')

    dc_candidates = []

    for way in data:
        # Initialize the "dc_candidate" flag
        way['dc_candidate'] = False

        # Check if the frequency is "0"
        if 'frequency' in way['tags'] and str(way['tags']['frequency']) == '0':
            way['dc_candidate'] = True
            dc_candidates.append({'UID': way['UID'], 'voltage_level': way['voltage'], 
                                  'reason': 'tag "frequency" has value "0"'})
        
        # Check if the name contains "DC"
        if 'name' in way['tags'] and 'dc' in way['tags']['name'].lower():
            way['dc_candidate'] = True
            dc_candidates.append({'UID': way['UID'], 'voltage_level': way['voltage'], 
                                  'reason': 'tag "name" contains "DC"'})
        
        # Check if the number of cables is "1"
        if 'cables' in way['tags'] and str(way['tags']['cables']) == '1':
            way['dc_candidate'] = True
            dc_candidates.append({'UID': way['UID'], 'voltage_level': way['voltage'], 
                                  'reason': 'tag "cables" has value "1"'})

    if not dc_candidates:
        # Handle case where no DC candidates are found
        dc_candidates.append({'UID': 'No possible DC candidate in all ways of those selected voltage levels found!'})
        print('   ... no potentially DC lines found.')
    else:
        # Count unique DC candidates
        unique_dc_candidates = len(set([candidate['UID'] for candidate in dc_candidates]))
        print(f'   ... {unique_dc_candidates} ways could potentially be a DC line.')
        print('   ... Please refer in workspace to variable DC candidates to manually check them if necessary!')

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data, dc_candidates

def my_count_cables(data):
    """
    DESCRIPTION
    This function checks for every way element the number of cables, adds
    them to the dataset and to a separate variable "cables_per_way". If a
    line obviously carries 2, 3 or 4 systems, a flag will be set
    accordingly and that way will be doubled, tripled or quadrupled in a
    later function.

    INPUT
    data ... dataset of selected ways

    OUTPUT
    data ... updated dataset with new fields "num_of_cables" and "systems"
    """
    start_time = time.time()
    print('Start counting cables per way...')

    cables_per_way = []

    for way in data:
        if 'cables' in way['tags']:
            try:
                # Convert cable count to integer
                num_of_cables = int(way['tags']['cables'])
            except ValueError:
                # Warn the user if the cable count is invalid
                print(f'   ATTENTION! Unknown cable number ("{way["tags"]["cables"]}") in UID {way["UID"]}. This way wont be cloned automatically.')
                continue

            way['cables'] = num_of_cables
            cables_per_way.append({'UID': way['UID'], 'num_of_cables': num_of_cables})

            # Determine the number of systems based on cable count
            if num_of_cables == 6:
                way['systems'] = 2
            elif num_of_cables == 9:
                way['systems'] = 3
            elif num_of_cables == 12:
                way['systems'] = 4
            else:
                way['systems'] = None
        else:
            # If no cable information is provided
            way['systems'] = None

    if not cables_per_way:
        # Handle case where no cable information is available
        print('   ... the ways in this voltage level selection don\'t provide information about number of cables...')
        cables_per_way.append({'UID': 'No information about number of cables provided in this selection.'})
    else:
        # Display cable statistics
        cables_unique, cables_occurance = np.unique([cable['num_of_cables'] for cable in cables_per_way], return_counts=True)
        print('\n')
        print(f"{'cables_per_way':>15} {'number_of_ways':>15}")
        for unique, occurance in zip(cables_unique, cables_occurance):
            print(f"{unique:>15} {occurance:>15}")

        print(f'   ... {len(data) - sum(cables_occurance)} ways with unknown number of cables.')
        print('   ... ways with 6 cables will be doubled, ways with 9 cables tripled and ways with 12 cables quadrupled.')
        print('   ... Please refer in workspace to variable "cables_per_way" to manually check other ways (DC? Traction Current? Unused cable?) if necessary.')

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data


def my_calc_distances_between_endpoints(data, degrees_to_km_conversion, bool_plot):
    """
    DESCRIPTION
    This function creates a Matrix "M" or "distances" with all distances
    between all endpoints. "M" would be a diagonal symmetrical Matrix
    (distances A to B is equal to distances B to A), so all elements in
    the south-west diagonal half will be set to "NaN". Distances
    between the same element (distance A to A or B to B) will be set to
    "-1" since this is an impossible distance value and therefore
    distinguishable. The correct value would be "0", but since we are
    looking specifically for stacked endnodes (distance A to B equals 0)
    the true value ("0") will not be used. Optionally a histogram of all
    distances can be plotted - this can be very useful to set the
    neighbouring threshold value.

    INPUT
    data ... dataset of all selected ways
    bool_plot ... boolean selector to optionally plot a histogram.

    OUTPUT
    M ... matrix with all distances between all endpoints
    """

    start_time = time.time()
    print('Start calculating distances between all endpoints... (takes a few seconds)')

    # Preallocate the distance matrix with NaN-elements
    num_data = len(data)
    M = np.full((num_data * 2, num_data * 2), np.nan)

    # Extract degrees to km conversion data into variables
    km_per_lon_deg = degrees_to_km_conversion[0]
    km_per_lat_deg = degrees_to_km_conversion[1]

    # Go through each row of distance matrix
    for i_row in range(num_data):
        # Create the 4x4 field of the current row, which will calculate
        # distances to all other endnodes
        data_column = np.array([[data[i_row].get('lon1_final', data[i_row]['lon1']), 
                                 data[i_row].get('lat1_final', data[i_row]['lat1'])],
                                [data[i_row].get('lon2_final', data[i_row]['lon2']), 
                                 data[i_row].get('lat2_final', data[i_row]['lat2'])]])

        # Every iteration this row gets smaller by one 4x4 block. Therefore
        # delete the first coordinates from previous run
        remaining_data = data[i_row+1:]

        # Preallocate the row vector
        data_row = np.zeros((2, len(remaining_data) * 2))

        # Copy all coordinates in alternating order to the row
        data_row[0, 0::2] = [way.get('lon1_final', way['lon1']) for way in remaining_data]
        data_row[0, 1::2] = [way.get('lon2_final', way['lon2']) for way in remaining_data]
        data_row[1, 0::2] = [way.get('lat1_final', way['lat1']) for way in remaining_data]
        data_row[1, 1::2] = [way.get('lat2_final', way['lat2']) for way in remaining_data]

        # Calc absolute distance in degree between lon/lat coordinates
        lon_deltas_to_lon1_deg = data_column[0, 0] - data_row[0, :]
        lon_deltas_to_lon2_deg = data_column[1, 0] - data_row[0, :]
        lat_deltas_to_lat1_deg = data_column[0, 1] - data_row[1, :]
        lat_deltas_to_lat2_deg = data_column[1, 1] - data_row[1, :]

        # Convert the delta_degree to delta_kilometer
        lon_deltas_to_lon1_km = lon_deltas_to_lon1_deg * km_per_lon_deg
        lon_deltas_to_lon2_km = lon_deltas_to_lon2_deg * km_per_lon_deg
        lat_deltas_to_lat1_km = lat_deltas_to_lat1_deg * km_per_lat_deg
        lat_deltas_to_lat2_km = lat_deltas_to_lat2_deg * km_per_lat_deg

        # Use Pythagoras to calculate distances between endpoints
        M_new_row = np.zeros((2, len(remaining_data) * 2))
        M_new_row[0, :] = np.sqrt(lon_deltas_to_lon1_km**2 + lat_deltas_to_lat1_km**2)
        M_new_row[1, :] = np.sqrt(lon_deltas_to_lon2_km**2 + lat_deltas_to_lat2_km**2)

        # Apply the newly calculated distance row to the distance matrix
        M[2*i_row:2*i_row+2, 2*i_row+2:] = M_new_row
        M[2*i_row:2*i_row+2, 2*i_row:2*i_row+2] = -1

    # Plot a Histogram of all the distances
    if bool_plot.histogram_distances_between_endpoints:
        print('   ... start visualizing all distances in a histogram ...')

        h = plt.figure()
        # Set windows size double the standard length
        h.set_size_inches(h.get_size_inches()[0], h.get_size_inches()[1] * 2)

        plt.subplot(5, 1, 1)
        plt.hist(M[~np.isnan(M)], bins=200)
        plt.title('Distances between all endnodes')
        plt.ylabel('number of pairs')
        plt.xlabel('distance [km]')

        plt.subplot(5, 1, 2)
        plt.hist(M[~np.isnan(M)], bins=200, range=(0, 10))
        plt.ylabel('number of pairs')
        plt.xlabel('distance [km]')

        plt.subplot(5, 1, 3)
        plt.hist(M[~np.isnan(M)], bins=400, range=(-1.5, 2))
        plt.ylabel('number of pairs')
        plt.xlabel('distance [km]')

        plt.subplot(5, 1, 4)
        plt.hist(M[~np.isnan(M)], bins=300, range=(0, 0.3))
        plt.ylabel('number of pairs')
        plt.xlabel('distance [km]')

        plt.subplot(5, 1, 5)
        plt.hist(M[~np.isnan(M)], bins=300, range=(0 + np.finfo(float).eps, 0.3))
        plt.ylabel('number of pairs')
        plt.xlabel('distance [km]')

        plt.show()

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return M


def my_calc_stacked_endnodes(data, distances, settings):
    """
    DESCRIPTION
    This function searches every distance combination between all
    endpoints which have the value "0", which means that two endpoints
    have the same coordinates and are stacked on top of each other. (This
    is easy to do and drastically increases computing performance in
    upcoming functions). Since in the distance Matrix M every endnode
    needs two rows/columns, the original "ID" will be recalculate to get
    the right way element. To the dataset a boolean flag will be added to
    determine if endnode1/2 is stacked. A list of all pairs of stacked
    endnodes will be return for further grouping. Optionally data of all
    stacked endnodes can be plotted and also a histogram of how many
    endnodes are stacked can be shown.
    
    INPUT
    data ... input dataset
    distances ... distance Matrix M which contains distances between all
                  endnodes
    settings ... boolean selector variable to toggle on/off the visualisations
    
    OUTPUT
    data ... updated dataset, new flag: endnode1/2_stacked
    nodes_stacked_pairs ... a raw list of all pairs of stacked endnodes
    """

    start_time = time.time()
    print('Start finding all stacked endnodes...')

    # Get the way ids of stacked elements
    # Create boolean logical index of all distance combinations which equal 0
    b_dist_is_zero = distances == 0

    # if no distance element has value 0, cancel that function since no two
    # endpoints are stacked
    if not np.any(b_dist_is_zero):
        # Set all boolean flags to false
        for way in data:
            way['node1_stacked'] = False
            way['node2_stacked'] = False
         
        # Create empty pseudo output
        nodes_stacked_pairs = []
        
        # Print this information to console
        print('   ... no endnode is stacked! \n')
        
        # End that function
        print('   ... finished! (%5.3f seconds) \n \n' % (time.time() - start_time))
        return data, nodes_stacked_pairs
    
    # Get the indices of this boolean matrix, hence the row/column IDs
    row_indices, col_indices = np.where(b_dist_is_zero)
    
    # Combine the row(y)- and column(x)-indices in one list and sort them
    # MATLAB sorts indices in column-major order, so we need to sort accordingly
    combined_indices = np.array([(i, j) for i, j in zip(row_indices, col_indices)])
    combined_indices = combined_indices[np.lexsort((combined_indices[:, 0], combined_indices[:, 1]))]
    
    # Separate the combined indices back into rows and columns
    row_indices = combined_indices[:, 0]
    col_indices = combined_indices[:, 1]
    
    # Combine the row(y)- and column(x)-indices in one list and sort them
    nodes_stacked_indices_combined = np.sort(np.hstack((row_indices, col_indices)))
    
    # remove duplicates: extract unique ids and calculate their occurrences
    nodes_stacked_indices_unique, nodes_stacked_indices_occurance = np.unique(nodes_stacked_indices_combined, return_counts=True)
    
    print('   ... %d endnodes are stacked! \n' % nodes_stacked_indices_unique.size)
    
    # Create new table, first column: unique indices
    # In this following code snippet, some changes were made in comparison to the original code
    # the calculation of the way id was a little bit altered by first adding 1 and after the divison
    # by 2 the 1 is added again, and the result for the endnode1 booleans was inversed, since this
    # values confine with the values we get from matlab
    nodes_stacked = {
        'index': nodes_stacked_indices_unique,
        'way_ID': np.ceil(((nodes_stacked_indices_unique + 1) / 2) - 1).astype(int),
        'endnode1': nodes_stacked_indices_unique % 2 == 0
    }

    # return all pairs, to group them later in another function      
    nodes_stacked_pairs = np.vstack((row_indices, col_indices)).T

    # Add stacked information to dataset
    # Start with first index
    i_stacked_nodes = 0
    
    # Initialize frequently used variable
    numel_way_IDs = len(nodes_stacked['way_ID'])
    
    # go through all ways in data_ways_selected
    for i_ways in range(len(data)):
        # Catch out-of-index-error if very last index (last way, endnode 2)
        # is stacked: Then break the loop
        if i_stacked_nodes >= len(nodes_stacked['way_ID']):
            break
        
        # Does current way (from data_ways_selected) contain a stacked endnode? 
        if i_ways == nodes_stacked['way_ID'][i_stacked_nodes]:
            # Yes, at least one endnode is stacked

            # Are both endnodes stacked?
            # Check if it's not the last way_ID AND next way_ID is identical
            if (i_stacked_nodes + 1 < numel_way_IDs) and (nodes_stacked['way_ID'][i_stacked_nodes] == nodes_stacked['way_ID'][i_stacked_nodes + 1]):
                # Yes, both endnodes are stacked
                data[i_ways]['node1_stacked'] = True
                data[i_ways]['node2_stacked'] = True

                # Skip one index, since we just set two nodes
                i_stacked_nodes += 1 
               
            # No, not both. So only one. Is endnode 1 stacked?  
            elif nodes_stacked['endnode1'][i_stacked_nodes] == 1:
                # Yes, endnode 1 is stacked
                data[i_ways]['node1_stacked'] = True
                data[i_ways]['node2_stacked'] = False

            # No, endnode 1 is not stacked
            else:
                # So endnode 2 must be stacked
                data[i_ways]['node1_stacked'] = False
                data[i_ways]['node2_stacked'] = True
            
            # select next index to compare against way_ID
            i_stacked_nodes += 1
          
        else:
            # No, none of both endnodes are stacked
            data[i_ways]['node1_stacked'] = False
            data[i_ways]['node2_stacked'] = False
    
    print('   ... finished! (%5.3f seconds) \n \n' % (time.time() - start_time))

    # Visualize this stacked data
    if settings.plot_stacked_endnodes:
        print('Start visualizing all stacked endnodes (takes a few seconds) ...')
        tic_viz = time.time()
        
        # Extract all nodes
        x = np.array([[way['x1'] for way in data], [way['x2'] for way in data]])
        y = np.array([[way['y1'] for way in data], [way['y2'] for way in data]])
        
        # Extract node1 if it is stacked, else ignore it    
        x_node1_stacked = x[0, [way['node1_stacked'] for way in data]]
        y_node1_stacked = y[0, [way['node1_stacked'] for way in data]]
                    
        # Extract node2 if it is stacked, else ignore it
        x_node2_stacked = x[1, [way['node2_stacked'] for way in data]]
        y_node2_stacked = y[1, [way['node2_stacked'] for way in data]]       
      
        # Plot all nodes, highlight node1 and node2 if stacked
        plt.figure(figsize=(10,4.6))
        plt.title('All ways with endnodes STACKED on XY-Map')
        plt.grid(True)
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        
        plt.plot(x, y, 'ok-')
        plt.plot(x_node1_stacked, y_node1_stacked, 'xr')
        plt.plot(x_node2_stacked, y_node2_stacked, '+b')
        
        plt.show()
        
        print('   ... finished! (%5.3f seconds) \n \n' % (time.time() - tic_viz))
    
    # plot histogram how many endnodes are stacked
    if settings.histogram_stacked_endnodes:
        plt.figure(figsize=(10,4.6))
        plt.hist(nodes_stacked_indices_occurance + 1)
        plt.title('Stacked endnodes: If stacked, how many are stacked?')
        plt.xlabel('Nodes stacked on top of each other')
        plt.ylabel('Number of different positions this occurs in')
        plt.show()

    return data, nodes_stacked_pairs


def my_calc_neighbouring_endnodes(data, distances, neighbourhood_threshold, settings):
    """
    DESCRIPTION
    This function searches every distance combination between all
    endpoints which have a distance value bigger than "0" (the "0" case
    was covered before) and lower then the treshold in
    "neighbourhood_treshhold", which means that two endpoints
    are in the vicinity, aka neighbourhood, to each other.
    Since in the distance Matrix M every endnode needs two rows/columns, 
    the original "ID" will be recalculate to get the right way element. 
    To the dataset a boolean flag will be added to determine if endnode1/2
    is in a neighbourhood. A list of all pairs of neighbouring endnodes will
    be return for further grouping. Optionally data of all
    neighbouring endnodes can be plotted and also a histogram of how many 
    endnodes are in a neighbourhood can be shown.
    
    INPUT
    data ... input dataset
    distances ... distance Matrix M which contains distances between all
                  endnodes
    neighbourhood_threshold ... threshold-radius to determine if a
                                endnode is in a neighbourhood or not
    settings ... settings object with plot options
    
    OUTPUT
    data ... updated dataset, new flag: endnode1/2_neighbour
    nodes_neighbouring_pairs ... list of all pairs of neighbouring endnodes
    """
    start_time = time.time()
    print('Start finding all neighbouring endnodes...')
    
    # Initialize 'node1_neighbour' and 'node2_neighbour' attributes
    for way in data:
        way['node1_neighbour'] = False
        way['node2_neighbour'] = False
    
    # Create boolean logical index of all combinations which are in
    # neighbourhood, but still not stacked
    b_dist_neighbourhood = (distances < neighbourhood_threshold) & (distances > 0)
    
    # if no element is in neighbourhood region, cancel that function
    if not np.any(b_dist_neighbourhood):
        print('   ... no endnode is in a neighbourhood!')
        nodes_neighbouring_pairs = []
        print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
        return data, nodes_neighbouring_pairs
    
    # Get the indices of this boolean matrix, hence the row/column IDs
    row_indices, col_indices = np.where(b_dist_neighbourhood)
    
    # Combine the row(y)- and column(x)-indices in one list and sort them
    # MATLAB sorts indices in column-major order, so we need to sort accordingly
    combined_indices = np.array([(i, j) for i, j in zip(row_indices, col_indices)])
    combined_indices = combined_indices[np.lexsort((combined_indices[:, 0], combined_indices[:, 1]))]
    
    # Separate the combined indices back into rows and columns
    row_indices = combined_indices[:, 0]
    col_indices = combined_indices[:, 1]
    
    # Combine the row(y)- and column(x)-indices in one list and sort them
    nodes_neighbouring_indices_combined = np.sort(np.hstack((row_indices, col_indices)))
    
    # remove duplicates: extract unique ids and calculate their occurrences
    nodes_neighbouring_indices_unique, nodes_neighbouring_indices_occurance = np.unique(nodes_neighbouring_indices_combined, return_counts=True)
    
    print('   ... %d endnodes are in same neighbourhood!' % len(nodes_neighbouring_indices_unique))
    
    # Create a list of unique neighbouring nodes
    nodes_neighbouring = [{'index': idx, 'way_ID': idx // 2, 'endnode1': (idx % 2 == 0)} for idx in nodes_neighbouring_indices_unique]
    
    # Group nodes into pairs
    #nodes_neighbouring_pairs = [(neighbour_indices[i, 0], neighbour_indices[i, 1]) for i in range(len(neighbour_indices))]
    nodes_neighbouring_pairs = np.vstack((row_indices, col_indices)).T
    
    # Add neighbouring information to dataset
    for node in nodes_neighbouring:
        way_ID = node['way_ID']
        endnode1 = node['endnode1']
        
        if endnode1:
            data[way_ID]['node1_neighbour'] = True
        else:
            data[way_ID]['node2_neighbour'] = True
    
    print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
    
    # Visualize this neighbouring data
    if settings.plot_neighbouring_endnodes:        
        print('Start visualizing all neighbouring endnodes (takes a few seconds)...')
        
        # Extract all nodes
        x = np.array([[way['x1'], way['x2']] for way in data])
        y = np.array([[way['y1'], way['y2']] for way in data])
        
        # Extract node1 if it is in a neighbourhood, else ignore it
        x_node1_neighbour = x[:, 0][[way['node1_neighbour'] for way in data]]
        y_node1_neighbour = y[:, 0][[way['node1_neighbour'] for way in data]]
        
        # Extract node2 if it is in a neighbourhood, else ignore it
        x_node2_neighbour = x[:, 1][[way['node2_neighbour'] for way in data]]
        y_node2_neighbour = y[:, 1][[way['node2_neighbour'] for way in data]]
        
        # Plot all nodes, highlight node1 and node2 if in neighbourhood
        plt.figure(figsize=(10,4.6))
        plt.title('All ways with endnodes NEIGHBOURING on XY-Map')
        plt.grid(True)
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        
        for way in data:
            plt.plot([way['x1'], way['x2']], [way['y1'], way['y2']], 'ok-')
        
        plt.plot(x_node1_neighbour, y_node1_neighbour, 'xr')
        plt.plot(x_node2_neighbour, y_node2_neighbour, '+b')
        
        plt.show()
        
        print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
    
    # Plot histogram of how many endnodes are in the neighbourhood
    if settings.histogram_neighbouring_endnodes:        
        plt.figure(figsize=(10,4.6))
        plt.hist(nodes_neighbouring_indices_occurance, bins=np.max(nodes_neighbouring_indices_occurance))
        plt.title('Neighbouring endnodes: How many will be in one group?')
        plt.xlabel('Number of nodes which will be grouped together')
        plt.ylabel('Number of different positions this occurs in')
        plt.show()
    
    return data, nodes_neighbouring_pairs


import time
import numpy as np

def my_group_nodes(pairs_input):
    """
    DESCRIPTION
    This function takes as input a list of pairs (stacked_pairs or
    neighbouring_pairs) to group them. This function checks all cases,
    hence creates new groups, adds elements to an existing group, and even
    concatenates groups.

    INPUT
    pairs_input ... list of pairs

    OUTPUT
    list ... a list of groups made out of the pairs from pairs_input
    """
    start_time = time.time()
    print(f'Start grouping all pairs from "{pairs_input}" (may take a few seconds)...')

    list_groups = []  # Initialize an empty list to store the grouped pairs

    # Sort each pair in ascending order for consistent processing
    pairs_sorted_horizontally = np.sort(pairs_input, axis=1)

    # Sort the entire list of pairs based on the first column and then the second column
    # This ensures that the pairs are processed in an ordered manner, similar to MATLAB sorting behavior
    pairs_sorted_vertically = pairs_sorted_horizontally[np.lexsort((pairs_sorted_horizontally[:, 1], pairs_sorted_horizontally[:, 0]))]

    # Iterate through each sorted pair
    for partner1, partner2 in pairs_sorted_vertically:
        # Find which group, if any, contains partner1
        row_partner1 = next((i for i, group in enumerate(list_groups) if partner1 in group), None)
        # Find which group, if any, contains partner2
        row_partner2 = next((i for i, group in enumerate(list_groups) if partner2 in group), None)

        if row_partner1 is not None:  # If partner1 already belongs to a group
            if row_partner2 is not None:  # If partner2 also belongs to a group
                if row_partner1 != row_partner2:  # If they are in different groups, merge them
                    list_groups[row_partner1].update(list_groups[row_partner2])  # Merge groups
                    list_groups.pop(row_partner2)  # Remove the now redundant group
            else:
                list_groups[row_partner1].add(partner2)  # Add partner2 to partner1's group
        elif row_partner2 is not None:  # If only partner2 belongs to a group
            list_groups[row_partner2].add(partner1)  # Add partner1 to partner2's group
        else:  # If neither partner is in any existing group, create a new group
            list_groups.append({partner1, partner2})

    # Convert each group from a set to a sorted list for structured output
    list_groups = [sorted(list(group)) for group in list_groups]

    # Print summary statistics
    total_nodes = sum(len(group) for group in list_groups)
    total_groups = len(list_groups)
    avg_nodes_per_group = total_nodes / total_groups if total_groups > 0 else 0

    print(f'   ... {total_nodes} nodes will be grouped together in {total_groups} grouped nodes,')
    print(f'       with an average of {avg_nodes_per_group:.2f} nodes per grouped node.')
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')

    return list_groups  # Return the final grouped node structure

def my_group_stacked_endnodes(data, nodes_stacked_grouped):
    """
    DESCRIPTION
    This function gets the ID and lon/lat/x/y coordinates of the first
    member of a stacked group and copies it to all the other members of
    that group, therefore giving all members the same node ID and
    (exactly) same coordinate.
    
    INPUT
    data ... original dataset
    nodes_stacked_grouped ... list of nodes which are stacked
    
    OUTPUT
    data ... updated dataset where all stacked nodes have the same group
             node id
    """
    start_time = time.time()
    print('Start adding coordinates of stacked groups...')

    # Preallocate new fields, so that they are in the right order
    for way in data:
        way['ID_node1_grouped'] = np.nan
        way['ID_node2_grouped'] = np.nan
        way['lon1_grouped'] = np.nan
        way['lat1_grouped'] = np.nan
        way['lon2_grouped'] = np.nan
        way['lat2_grouped'] = np.nan
        way['x1_grouped'] = np.nan
        way['y1_grouped'] = np.nan
        way['x2_grouped'] = np.nan
        way['y2_grouped'] = np.nan

    # Extract first group coordinates of all stacked groups
    for i_group in range(len(nodes_stacked_grouped)):
        # Save the node_ID of first group member
        i_node_ID = nodes_stacked_grouped[i_group][0]

        # Convert the node_ID in the way_ID (adjusting for Python's zero-based indexing)
        i_way_ID = math.ceil((i_node_ID + 1)/2) - 1
        
        # Extract from the node_ID the boolean information, if  
        # it is node1 (true) or node2 (false)
        b_node1 = ((i_node_ID + 1) % 2) == 1

        if b_node1:
            # get ID/coordinates of node 1
            grouped_node_ID = data[i_way_ID]['ID_node1']
            grouped_lat = data[i_way_ID]['lat1']
            grouped_lon = data[i_way_ID]['lon1']        
            grouped_x = data[i_way_ID]['x1']
            grouped_y = data[i_way_ID]['y1'] 
        else:
            # get ID/coordinates of node 2
            grouped_node_ID = data[i_way_ID]['ID_node2']
            grouped_lat = data[i_way_ID]['lat2']
            grouped_lon = data[i_way_ID]['lon2']
            grouped_x = data[i_way_ID]['x2']
            grouped_y = data[i_way_ID]['y2'] 

        # go through every (nonzero) member of that group       
        for i_group_member in range(len(nodes_stacked_grouped[i_group])):
            #if nodes_stacked_grouped[i_group][i_group_member] == 0:
            #    continue

            # Save the node_ID of that group member
            i_node_ID = nodes_stacked_grouped[i_group][i_group_member]

            # Convert the node_ID in the way_ID (adjusting for Python's zero-based indexing)
            i_way_ID = math.ceil((i_node_ID + 1)/2) - 1

            # Extract from the node_ID the boolean information, if  
            # it is node1 (true) or node2 (false)
            b_node1 = ((i_node_ID + 1) % 2) == 1

            if b_node1:
                # add the new combined id/lat/lon
                data[i_way_ID]['ID_node1_grouped'] = grouped_node_ID
                data[i_way_ID]['lat1_grouped'] = grouped_lat
                data[i_way_ID]['lon1_grouped'] = grouped_lon
                data[i_way_ID]['x1_grouped'] = grouped_x
                data[i_way_ID]['y1_grouped'] = grouped_y                
            else:
                # add the new combined id/lat/lon
                data[i_way_ID]['ID_node2_grouped'] = grouped_node_ID
                data[i_way_ID]['lat2_grouped'] = grouped_lat
                data[i_way_ID]['lon2_grouped'] = grouped_lon
                data[i_way_ID]['x2_grouped'] = grouped_x
                data[i_way_ID]['y2_grouped'] = grouped_y     

    print('   ... finished! (%5.3f seconds) \n' % (time.time() - start_time))
    return data

def my_group_neighbouring_endnodes(data, nodes_neighbouring_grouped, degrees_to_km_conversion):
    """
    DESCRIPTION
    This function extracts all lon/lat coordinates of all members for every
    neighbouring group, then calculates the mean lon/lat value and copies
    it to every group member. Then the x/y values will newly be
    calculated and too added.
    
    INPUT
    data ... origial input dataset
    nodes_neighbouring_grouped ... list with nodes grouped
    degrees_to_km_conversion ... conversion data to calculate x/y coordinates
    
    OUTPUT
    data ... updated dataset with grouped fields
    grouped_xy_coordinates ... list of x/y coordinates of grouped nodes,
                               this will be used in a plot later
    """
    start_time = time.time()
    print('Start adding grouping neighbours...')

    # Initialize variables for group processing
    num_of_groups = len(nodes_neighbouring_grouped)
    max_group_size = max(len(group) for group in nodes_neighbouring_grouped)

    # Preallocate arrays to store grouped coordinates
    grouped_lonlat_coordinates = np.zeros((num_of_groups, max_group_size * 2))
    grouped_xy_coordinates = np.zeros((num_of_groups, max_group_size * 2))

    # Process each group and extract coordinates for each member
    for i_group in range(num_of_groups):
        for i_group_member in range(len(nodes_neighbouring_grouped[i_group])):
            i_node_ID = nodes_neighbouring_grouped[i_group][i_group_member]
            i_way_ID = math.ceil((i_node_ID + 1) / 2) - 1
            b_node1 = ((i_node_ID + 1) % 2) == 1

            # Assign coordinates based on whether it's the first or second node
            if b_node1:
                lon = data[i_way_ID]['lon1']
                lat = data[i_way_ID]['lat1']
                x = data[i_way_ID]['x1']
                y = data[i_way_ID]['y1']
            else:
                lon = data[i_way_ID]['lon2']
                lat = data[i_way_ID]['lat2']
                x = data[i_way_ID]['x2']
                y = data[i_way_ID]['y2']

            # Store the coordinates in preallocated arrays
            if i_group_member == 0:
                grouped_lonlat_coordinates[i_group, 0] = lon
                grouped_lonlat_coordinates[i_group, 1] = lat
                grouped_xy_coordinates[i_group, 0] = x
                grouped_xy_coordinates[i_group, 1] = y
            else:
                grouped_lonlat_coordinates[i_group, i_group_member * 2] = lon
                grouped_lonlat_coordinates[i_group, i_group_member * 2 + 1] = lat
                grouped_xy_coordinates[i_group, i_group_member * 2] = x
                grouped_xy_coordinates[i_group, i_group_member * 2 + 1] = y

    # Calculate mean lon/lat for each group
    list_coordinates_mean = np.zeros((num_of_groups, 2))
    for i_group in range(num_of_groups):
        lon_data = grouped_lonlat_coordinates[i_group, 0::2]
        lat_data = grouped_lonlat_coordinates[i_group, 1::2]

        # Filter out zero values before calculating the mean
        lon_data = lon_data[lon_data != 0]
        lat_data = lat_data[lat_data != 0]

        list_coordinates_mean[i_group, 0] = np.mean(lon_data)
        list_coordinates_mean[i_group, 1] = np.mean(lat_data)

    # Assign mean coordinates to grouped nodes
    for i_group in range(num_of_groups):
        for i_group_member in range(len(nodes_neighbouring_grouped[i_group])):
            i_node_ID = nodes_neighbouring_grouped[i_group][i_group_member]
            i_way_ID = math.ceil((i_node_ID + 1) / 2) - 1
            b_node1 = ((i_node_ID + 1) % 2) == 1

            if b_node1:
                data[i_way_ID]['ID_node1_grouped'] = i_group + 1
                data[i_way_ID]['lon1_grouped'] = list_coordinates_mean[i_group, 0]
                data[i_way_ID]['lat1_grouped'] = list_coordinates_mean[i_group, 1]
            else:
                data[i_way_ID]['ID_node2_grouped'] = i_group + 1
                data[i_way_ID]['lon2_grouped'] = list_coordinates_mean[i_group, 0]
                data[i_way_ID]['lat2_grouped'] = list_coordinates_mean[i_group, 1]

    # Convert degrees to kilometers using the provided conversion factors
    km_per_lon_deg, km_per_lat_deg, mean_lon, mean_lat = degrees_to_km_conversion

    delta_lon1 = np.array([way['lon1_grouped'] for way in data if way['lon1_grouped'] is not None]) - mean_lon
    delta_lon2 = np.array([way['lon2_grouped'] for way in data if way['lon2_grouped'] is not None]) - mean_lon
    delta_lat1 = np.array([way['lat1_grouped'] for way in data if way['lat1_grouped'] is not None]) - mean_lat
    delta_lat2 = np.array([way['lat2_grouped'] for way in data if way['lat2_grouped'] is not None]) - mean_lat

    # Calculate x/y coordinates for grouped nodes
    x1 = delta_lon1 * km_per_lon_deg
    x2 = delta_lon2 * km_per_lon_deg
    y1 = delta_lat1 * km_per_lat_deg
    y2 = delta_lat2 * km_per_lat_deg

    # Update the dataset with calculated x/y coordinates
    for i, way in enumerate(data):
        if way.get('lon1_grouped') is not None:
            way['x1_grouped'] = x1[i]
            way['y1_grouped'] = y1[i]
        if way.get('lon2_grouped') is not None:
            way['x2_grouped'] = x2[i]
            way['y2_grouped'] = y2[i]

    # Handle cases where grouped data is not available
    for way in data:
        if np.isnan(way.get('ID_node1_grouped', np.nan)):
            way['ID_node1_grouped'] = None
            way['x1_grouped'] = None
            way['y1_grouped'] = None
            way['lon1_grouped'] = None
            way['lat1_grouped'] = None

        if np.isnan(way.get('ID_node2_grouped', np.nan)):
            way['ID_node2_grouped'] = None
            way['x2_grouped'] = None
            way['y2_grouped'] = None
            way['lon2_grouped'] = None
            way['lat2_grouped'] = None

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data, grouped_xy_coordinates


def my_add_final_coordinates(data):
    """
    DESCRIPTION
    This function selects the final coordinates: If one or both endnodes
    got grouped (because they were stacked and/or in a neighbourhood),
    those new grouped coordinates will be the final coordinates. If not,
    then the original coordinates will be taken as the final coordinates.
    The final coordinate will consist of the ID, the lon/lat, and the x/y
    coordinates.
    
    INPUT
    data ... original dataset
    
    OUTPUT
    data ... updated dataset with new final coordinates fields
    """
    start_time = time.time()
    print('Start adding final coordinates...')
    
    # First, go through all ways and get the new endnode coordinates
    for way in data:
        # Check if there is a new node 1, if not, take old one
        if not way.get('ID_node1_grouped'):
            way['ID_node1_final'] = way['ID_node1']
            way['lon1_final'] = way['lon1']
            way['lat1_final'] = way['lat1']
            way['x1_final'] = way['x1']
            way['y1_final'] = way['y1']
        else:
            way['ID_node1_final'] = way['ID_node1_grouped']
            way['lon1_final'] = way['lon1_grouped']
            way['lat1_final'] = way['lat1_grouped']
            way['x1_final'] = way['x1_grouped']
            way['y1_final'] = way['y1_grouped']

        # Check if there is a new node 2, if not, take old one
        if not way.get('ID_node2_grouped'):
            way['ID_node2_final'] = way['ID_node2']
            way['lon2_final'] = way['lon2']
            way['lat2_final'] = way['lat2']
            way['x2_final'] = way['x2']
            way['y2_final'] = way['y2']
        else:
            way['ID_node2_final'] = way['ID_node2_grouped']
            way['lon2_final'] = way['lon2_grouped']
            way['lat2_final'] = way['lat2_grouped']
            way['x2_final'] = way['x2_grouped']
            way['y2_final'] = way['y2_grouped']
    
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds)')
    return data

def my_delete_singular_ways(data):
    """
    DESCRIPTION
    This function deletes all ways which have the same endpoints after
    grouping, hence got "shrunk" into a singularity.

    INPUT
    data ... original dataset

    OUTPUT
    data ... new dataset with singularity-ways deleted
    """
    start_time = time.time()
    print('Start deleting ways which have the same endpoints after grouping...')
                      
    # Identify singular ways where both endpoints are identical after grouping
    way_IDs_singular = [i for i, way in enumerate(data) if way['ID_node1_final'] == way['ID_node2_final']]
    
    # Save the singular ways for potential debugging or review
    data_singular_ways = [data[i] for i in way_IDs_singular]
    
    # Remove singular ways from the dataset
    data = [way for i, way in enumerate(data) if i not in way_IDs_singular]
    
    print(f'   ... {len(way_IDs_singular)} ways were deleted!')
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    
    return data, data_singular_ways

def my_calc_real_lengths(data_ways_selected, data_ways_all, data_nodes_all, bool):
    """
    DESCRIPTION
    This function calculates the real length of a line. It fetches all
    coordinates off all nodes of all UIDs, calculates the length between
    those segments and adds them all up to calculate the real length.

    INPUT
    data_ways_selected ... from which ways the real length should be calculated
    data_ways_all ... no ways have been doubled here, so fetch data here
    data_nodes_all ... get all coordinates of all nodes
    bool ... toggle on / off the whole function and specify visualization

    OUTPUT
    data_ways_selected ... give each way its real line length
    lengths ... the struct used to calculate the real line lengths
    """
    
    print('Start calculating real length of lines...')
    
    if settings.calculate_real_line_length:
        start_time = time.time()

        # Get all the ways UIDs which real lengths we want to calculate
        unique_UIDs = np.unique([way['UID'] for way in data_ways_selected])

        # Create a list of all node ids
        list_all_node_IDs = np.array([node['id'] for node in data_nodes_all])

        # Initialize the reverse string for real-time percentage status update
        reverse_string = ''

        # Calculate the number of UID-Ways
        numel_uids = len(unique_UIDs)

        lengths = []

        # Go through every UID
        for i_uid, uid in enumerate(unique_UIDs):

            # Get the position of current UID in data_ways_all
            i_ways = next(i for i, way in enumerate(data_ways_all) if way['UID'] == uid)
            
            # Copy relevant information (UID, way_ID) of that UID
            current_length = {
                'UID': data_ways_all[i_ways]['UID'],
                'way_id': data_ways_all[i_ways]['id'],
                'nodes': []
            }

            # Go through every node of that UID
            for i_node, node_id in enumerate(data_ways_all[i_ways]['nodes']):

                # Find the position of current node id in list_all_node_IDs
                position_current_node = np.where(list_all_node_IDs == node_id)[0][0]

                # use this position to copy lon/lat coordinates of current node
                lon = data_nodes_all[position_current_node]['lon']
                lat = data_nodes_all[position_current_node]['lat']

                # Add coordinates of current node ID to that node
                current_length['nodes'].append({
                    'id': node_id,
                    'lon': lon,
                    'lat': lat
                })

                # Assign field "next coordinate"
                if i_node > 0:
                    current_length['nodes'][i_node - 1]['next_lon'] = lon
                    current_length['nodes'][i_node - 1]['next_lat'] = lat

            # Copy length as last field
            current_length['length_org'] = data_ways_all[i_ways]['length']
            lengths.append(current_length)

##            # (optional) Print progress to console
##            percent_done = 100 * (i_uid + 1) / numel_uids
##            string = f'   ... fetching coordinates of all nodes of way {i_uid + 1} of {numel_uids} ({percent_done:.2f} Percent)... \n'
##            print(reverse_string + string, end='')
##            reverse_string = '\b' * len(string)

        # Calculate beeline distance of each way
        print('   ... calculating length of each line segment...')

        # Set the earth radius in km
        earth_radius = 6371

        # Go through all UIDs
        for current_length in lengths:

            # Get start coordinate of each line segment in rad
            lon_start_rad = np.radians(current_length['nodes'][0]['lon'])
            lat_start_rad = np.radians(current_length['nodes'][0]['lat'])

            # Get end coordinate of each line segment in rad
            lon_end_rad = np.radians(current_length['nodes'][-1]['lon'])
            lat_end_rad = np.radians(current_length['nodes'][-1]['lat'])

            # Calculate difference between coordinates
            delta_lon_rad = lon_end_rad - lon_start_rad
            delta_lat_rad = lat_end_rad - lat_start_rad

            # Use Equirectangular approximation formula to calculate lengths
            x = delta_lon_rad * np.cos((lat_start_rad + lat_end_rad) / 2)
            y = delta_lat_rad
            length_of_line = np.sqrt(x ** 2 + y ** 2) * earth_radius

            # Add that length to each way element
            current_length['length_beeline'] = length_of_line

        # Calculate distances of each segment
        for current_length in lengths:

            # Get all starting coordinates of each line segment
            lons_start = [node['lon'] for node in current_length['nodes']]
            lats_start = [node['lat'] for node in current_length['nodes']]

            # Last node can't be a start coordinate
            lons_start = lons_start[:-1]
            lats_start = lats_start[:-1]

            # Get all ending coordinates of each line segment
            lons_end = [node.get('next_lon', np.nan) for node in current_length['nodes']]
            lats_end = [node.get('next_lat', np.nan) for node in current_length['nodes']]

            # Remove last element which is not valid
            lons_end = lons_end[:-1]
            lats_end = lats_end[:-1]

            # Convert degrees to radians
            lons_start_rad = np.radians(lons_start)
            lats_start_rad = np.radians(lats_start)
            lons_end_rad = np.radians(lons_end)
            lats_end_rad = np.radians(lats_end)

            # Calculate difference between coordinates
            delta_lons_rad = lons_end_rad - lons_start_rad
            delta_lats_rad = lats_end_rad - lats_start_rad

            # Use Equirectangular approximation formula to calculate lengths
            x = delta_lons_rad * np.cos((lats_start_rad + lats_end_rad) / 2)
            y = delta_lats_rad
            lengths_of_segments = np.sqrt(x ** 2 + y ** 2) * earth_radius

            # Go through all but last segments of current way
            for i_nodes in range(len(current_length['nodes']) - 1):
                current_length['nodes'][i_nodes]['segment_lengths'] = lengths_of_segments[i_nodes]

            # Add length of whole line (sum of segments) to current way element
            current_length['length_all_segments'] = np.sum(lengths_of_segments)
            
            # Add length-difference in percent
            current_length['length_diff_in_percent'] = (current_length['length_all_segments'] / current_length['length_beeline']) * 100 - 100

            # Add absolute length-difference in kilometers
            current_length['length_diff_absolut_in_km'] = current_length['length_all_segments'] - current_length['length_beeline']

            # Add length-difference between org/beeline in percent
            current_length['length_diff_between_org_and_beeline_percent'] = (current_length['length_org'] / current_length['length_beeline']) * 100 - 100

        # Add that length to data_ways_selected too
        for way in data_ways_selected:
            way['length_real'] = None
        
        for current_length in lengths:
            current_UID = current_length['UID']
            current_real_length = current_length['length_all_segments']
            
            # Create boolean index which elements have current UID
            for way in data_ways_selected:
                if way['UID'] == current_UID:
                    way['length_real'] = current_real_length

        # If needed, transpose lengths to match the other dimension
        lengths = np.array(lengths)

        if settings.plot_comparison_real_beeline:
            print('Start plotting comparison between real line course and beeline')
            # Visualization of those lengths
            plt.figure(figsize=(10,4.6))
            plt.title('Comparison between real line course and beeline')
            plt.xlabel('Longitude [°]')
            plt.ylabel('Latitude [°]')
            plt.grid(True)

            # Go through every UID
            for current_length in lengths:

                # Plot that way only if two criteria are met
                if (current_length['length_diff_in_percent'] > bool.beeline_visu_treshold_diff_percent and 
                    current_length['length_diff_absolut_in_km'] > bool.beeline_visu_treshold_diff_absolut):

                    # Plot line between endpoints with "x" as endpoint
                    bee_line_lon = [current_length['nodes'][0]['lon'], current_length['nodes'][-1]['lon']]
                    bee_line_lat = [current_length['nodes'][0]['lat'], current_length['nodes'][-1]['lat']]
                    plt.plot(bee_line_lon, bee_line_lat, 'x-k', linewidth=1, markersize=8)

                    # Plot real line course as colorful ".-" segments on top
                    lons_segments = [node['lon'] for node in current_length['nodes']]
                    lats_segments = [node['lat'] for node in current_length['nodes']]
                    plt.plot(lons_segments, lats_segments, '.-')

            plt.show()

    else:
        print('   ATTENTION: Real line length WONT be calculated!')
        print('              Beeline-length (Luftlinie) will be used.')
        lengths = "Real line lengths have NOT been calculated!"

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds)\n')
    return data_ways_selected, lengths


def my_get_tags(data):
    """
    DESCRIPTION
    Extract all tags from all way elements.

    INPUT
    data ... dataset prior to exporting

    OUTPUT
    data_tags ... all tags off all way elements
    """
    start_time = time.time()
    print('Start extracting all tags from all ways...')
    
    data_tags = []  # Initialize list to store tags for each way element
    
    for i, way in enumerate(data):
        # Skip duplicate entries if the previous element has the same UID
        if i > 0 and data_tags[-1]['UID'] == way['UID']:
            continue

        # Create a dictionary for the current way's tags
        tags = {'UID': way['UID']}

        # Ensure all tag values are encoded in UTF-8 for consistency
        encoded_tags = {
            k: v.encode('utf-8').decode('utf-8') if isinstance(v, str) else v
            for k, v in way['tags'].items()
        }

        # Merge the encoded tags into the dictionary
        tags.update(encoded_tags)
        data_tags.append(tags)  # Append the tag dictionary to the result list
    
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    
    return data_tags



def my_get_country_code_from_coordinates(mean_lon, mean_lat):
    """
    DESCRIPTION
    From the given coordinates, this function detects in which country
    the coordinates are located and automatically extract a country
    code which is the output of this function.
    
    INPUT
    lon ... mean longitude coordinate of the dataset coordinates
    lat ... mean latitude coordinate of the dataset coordinates

    OUTPUT
    country_data ... the attribute 'alpha_2' contains the information 
                     about the country code
    """
    
    # Create a point with the given coordinates
    point = Point(mean_lon, mean_lat)

    # load world shapefile
    world_gdf = gpd.read_file('ne_110m_admin_0_countries.shp')
    
    # Iteration through all countrys and checking, in which country the point is located
    for country in world_gdf.itertuples():
        geom = country.geometry
        country_name = getattr(country, 'NAME', None)  # Spaltenname anpassen, falls nötig
        
        # Split multi-polygons and check each part
        if isinstance(geom, MultiPolygon):
            for polygon in geom.geoms:
                if polygon.contains(point):
                    country_data = pycountry.countries.get(name=country_name)
                    if country_data:
                        return country_data.alpha_2
        # In case it is a single polygon
        elif isinstance(geom, Polygon):  
            if geom.contains(point):
                country_data = pycountry.countries.get(name=country_name)
                if country_data:
                    return country_data.alpha_2
    return None

def remove_duplicates(data):
    seen_pairs = set()  # Set for storing already seen pairs
    cleaned_data = []   # List for the cleaned data

    for way in data:
        # Extract the relevant values from the entry
        ID_node1_final = way.get('ID_node1_final')
        ID_node2_final = way.get('ID_node2_final')

        # Create a sorted tuple of the two IDs to detect duplicates (regardless of order)
        pair = tuple(sorted([ID_node1_final, ID_node2_final]))

        # If the pair has not been seen yet, add it to the cleaned list
        if pair not in seen_pairs:
            cleaned_data.append(way)
            seen_pairs.add(pair)  # Add the pair to the seen set

    return cleaned_data


def my_add_LtgsID_clone_ways(data, export_excel_country_code):
    """
    DESCRIPTION
    This function creates the "LtgsID" for every way element and adds a counter for cloned ways.

    INPUT
    data ... input dataset
    export_excel_country_code ... the two-digit country code 

    OUTPUT
    data_new ... new dataset with cloned ways and fields "LtgsID" and "CloneID"
    """
    import time  # Ensure the required module is available

    start_time = time.time()
    print('Start adding "LtgsID" and cloning ways...')
    
    num_of_ways = len(data)  # Total number of ways in the dataset
    num_of_doubled_ways = 0  # Counter for doubled ways
    num_of_tripled_ways = 0  # Counter for tripled ways
    num_of_quadrupled_ways = 0  # Counter for quadrupled ways
    data_new = []  # New dataset to include original and cloned ways
   
    # Create a prefix for LtgsID based on the country code
    LtgsID_Prefix = f'LTG{export_excel_country_code}'
    LtgsID = [f'{LtgsID_Prefix}{i:04d}' for i in range(1, num_of_ways + 1)]

    # Ensure all ways have a defined number of systems; default is 2
    for i in range(num_of_ways):
        if data[i]['systems'] is None:
            data[i]['systems'] = 2

    # Assign initial LtgsID and CloneID to each way
    for i in range(num_of_ways):
        data[i]['LtgsID'] = LtgsID[i]
        data[i]['CloneID'] = 'c1'  # Original way gets CloneID 'c1'
   
    # Clone ways based on the number of systems
    for way in data:
        current_clone_id = 1  # CloneID counter for the current way
        
        if way['systems'] == 2:
            # Double the way (create one clone)
            cloned_way_b = way.copy()
            LtgsID_current = way['LtgsID']  # Retain the same LtgsID
            way['CloneID'] = f'c{current_clone_id}'  # First copy
            current_clone_id += 1
            cloned_way_b['CloneID'] = f'c{current_clone_id}'  # Second copy
            data_new.extend([way, cloned_way_b])  # Add both to the new dataset
            num_of_doubled_ways += 1  # Increment double counter
        
        elif way['systems'] == 3:
            # Triple the way (create two clones)
            cloned_way_b = way.copy()
            cloned_way_c = way.copy()
            LtgsID_current = way['LtgsID']
            way['CloneID'] = f'c{current_clone_id}'  # First copy
            current_clone_id += 1
            cloned_way_b['CloneID'] = f'c{current_clone_id}'  # Second copy
            current_clone_id += 1
            cloned_way_c['CloneID'] = f'c{current_clone_id}'  # Third copy
            data_new.extend([way, cloned_way_b, cloned_way_c])  # Add all to the new dataset
            num_of_tripled_ways += 2  # Increment triple counter
        
        elif way['systems'] == 4:
            # Quadruple the way (create three clones)
            cloned_way_b = way.copy()
            cloned_way_c = way.copy()
            cloned_way_d = way.copy()
            LtgsID_current = way['LtgsID']
            way['CloneID'] = f'c{current_clone_id}'  # First copy
            current_clone_id += 1
            cloned_way_b['CloneID'] = f'c{current_clone_id}'  # Second copy
            current_clone_id += 1
            cloned_way_c['CloneID'] = f'c{current_clone_id}'  # Third copy
            current_clone_id += 1
            cloned_way_d['CloneID'] = f'c{current_clone_id}'  # Fourth copy
            data_new.extend([way, cloned_way_b, cloned_way_c, cloned_way_d])  # Add all to the new dataset
            num_of_quadrupled_ways += 3  # Increment quadruple counter
        
        else:
            # If the way has an unsupported number of systems, keep it unchanged
            data_new.append(way)

    # Print summary of cloning operations
    print(f'   ... {num_of_doubled_ways} ways have been doubled, '
          f'{num_of_tripled_ways // 2} tripled, '
          f'{num_of_quadrupled_ways // 3} quadrupled.')
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    
    return data_new


def my_export_excel(data, export_excel_country_code, data_tags, way_length_multiplier):
    """
    DESCRIPTION
    !!! OLD FORMAT !!!
    For the new format make sure to check the option lego_export = TRUE
    This function exports the data to two excel files. Every unique endnode
    will receive a NUID (unique node ID), this too will be added to the
    dataset. Columns will be created so that ATLANTIS can
    read the excel file. In the annotation ("Bemerkung") column additional
    information will be written if necessary.
    
    INPUT
    data ... the dataset to export
    export_excel_country_code ... the countrycode to name LtgsID and NUID
    data_tags ... all values of all fields of all tags of all way elements
    
    OUTPUT
    data ... updated dataset (NUID have been added)
    (two Excel files in current directory: tbl_Stamm_Leitungen & _Knoten)  
    """

    start_time = time.time()
    print('Start exporting data to Excel files... (may take a few seconds)')

    # Initialize and preallocate variables used in this script
    num_of_ways = len(data)

    # Assign NUID (=Node Unique ID)
    node1_data = np.zeros((num_of_ways, 4))
    node2_data = np.zeros((num_of_ways, 4))

    # Get relevant data of nodes
    node1_data[:, 0] = [way['ID_node1_final'] for way in data]
    node1_data[:, 1] = [way['voltage'] for way in data]
    node1_data[:, 2] = [way['lon1_final'] for way in data]
    node1_data[:, 3] = [way['lat1_final'] for way in data]

    node2_data[:, 0] = [way['ID_node2_final'] for way in data]
    node2_data[:, 1] = [way['voltage'] for way in data]
    node2_data[:, 2] = [way['lon2_final'] for way in data]
    node2_data[:, 3] = [way['lat2_final'] for way in data]

    # Get every unique node / voltage level combination
    nodes_unique = np.unique(np.vstack((node1_data, node2_data)), axis=0)

    # Create unique IDs for the nodes, "NUID" = Node_Unique_ID
    num_of_unique_nodes = nodes_unique.shape[0]
    counter = np.arange(1, num_of_unique_nodes + 1)
    nuid = [f'{export_excel_country_code}{str(i).zfill(5)}' for i in counter]

    # Combine the ID and the list of unique nodes into a conversion file
    nodes_conversion = np.column_stack((nuid, nodes_unique))

    # Go through every NUID and assign it to data where the node ID and the voltage level matches
    for i_nuid in range(len(nodes_unique)):
        node_org_ID = int(float(nodes_conversion[i_nuid, 1]))
        node_org_voltage = int(float(nodes_conversion[i_nuid, 2]))

        b_node1_ID_match = node1_data[:, 0] == node_org_ID
        b_node2_ID_match = node2_data[:, 0] == node_org_ID

        b_node1_voltage_match = node1_data[:, 1] == node_org_voltage
        b_node2_voltage_match = node2_data[:, 1] == node_org_voltage

        b_node1_id_and_voltage_ok = b_node1_ID_match & b_node1_voltage_match
        b_node2_id_and_voltage_ok = b_node2_ID_match & b_node2_voltage_match

        for way in data:
            if way['ID_node1_final'] == node_org_ID and way['voltage'] == node_org_voltage:
                way['node1_nuid'] = nuid[i_nuid]
            if way['ID_node2_final'] == node_org_ID and way['voltage'] == node_org_voltage:
                way['node2_nuid'] = nuid[i_nuid]

    str_annotation = ["" for _ in range(num_of_ways)]

    for i_ways in range(num_of_ways):
        if data[i_ways]['vlevels'] != 1:
            str_annotation[i_ways] += ", multiple vlevels"

        if data[i_ways]['systems'] == 2:
            str_annotation[i_ways] += ", 6 cables - 2 systems"
        elif data[i_ways]['systems'] == 3:
            str_annotation[i_ways] += ", 9 cables - 3 systems"
        elif data[i_ways]['systems'] == 4:
            str_annotation[i_ways] += ", 12 cables - 4 systems"

        if data[i_ways]['dc_candidate']:
            str_annotation[i_ways] += ", potentially DC"

        if not str_annotation[i_ways]:
            str_annotation[i_ways] = " "

    UID = [str(way['UID']) for way in data]
    Note = ["UID: " + uid + note for uid, note in zip(UID, str_annotation)]

    fromNode = [way['node1_nuid'] for way in data]
    toNode = [way['node2_nuid'] for way in data]
    Voltage = [way['voltage'] / 1000 for way in data]

    if 'length_real' in data[0]:
        Length = [way['length_real'] for way in data]
        print('INFO: Real line length got used (segmentwise calculation)!')
    else:
        Length = [way['length'] for way in data]
        print('INFO: simplified line length got used (beeline - Luftlinie)!')

    Length = np.round(np.array(Length) * way_length_multiplier, 2)
    print(f'INFO: Length of each line got multiplied by {way_length_multiplier:.2f} for slack compensation!')

    LineID = [way['LtgsID'] for way in data]
    Country = [export_excel_country_code] * num_of_ways

    R = X = Bc = Itherm = Capacity = PhiPsMax = [0] * num_of_ways

    str_timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
    str_cc = f'{export_excel_country_code}_'

    table_leitungen = pd.DataFrame({
        'LineID': LineID,
        'Country': Country,
        'fromNode': fromNode,
        'toNode': toNode,
        'Voltage': Voltage,
        'R': R,
        'X': X,
        'Bc': Bc,
        'Itherm': Itherm,
        'Length': Length,
        'Capacity': Capacity,
        'Note': Note,
        'PhiPsMax': PhiPsMax
    })

    folder_path = os.path.dirname(os.path.abspath(__file__)) + "/Excel-Files/"
    filename_lines = folder_path + f'Python_tbl_Lines_{str_cc}{str_timestamp}.xlsx'
    
    with pd.ExcelWriter(filename_lines, engine='xlsxwriter') as writer:
        table_leitungen.to_excel(writer, sheet_name='Sheet1', index=False)
        pd.DataFrame(data_tags).to_excel(writer, sheet_name='Sheet2', index=False)

    print('INFO: In "tbl_Lines.xlsx" in "Sheet 2" all tags from all UIDs are listed! Have a look for data inspection!')

    NodeID = nuid
    Country = [export_excel_country_code] * num_of_unique_nodes
    Voltage = nodes_conversion[:, 2].astype(float) / 1000
    lon = nodes_conversion[:, 3].astype(float)
    lat = nodes_conversion[:, 4].astype(float)

    table_knoten = pd.DataFrame({
        'NodeID': NodeID,
        'Country': Country,
        'Voltage': Voltage,
        'lat': lat,
        'lon': lon
    })

    filename_nodes = folder_path + f'Python_tbl_Nodes_{str_cc}{str_timestamp}.xlsx'

    with pd.ExcelWriter(filename_nodes, engine='xlsxwriter') as writer:
        table_knoten.to_excel(writer, sheet_name='Sheet1', index=False)
    
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')

    return data


def my_export_excel_lego(data, export_excel_country_code, data_tags, way_length_multiplier):
    """
    DESCRIPTION
    This function exports the data to two excel files in conformation with LEGO.
    Every unique endnode will receive a NUID (unique node ID), this too will be
    added to the dataset. Columns will be created so that LEGO can
    read the excel file. 
    
    INPUT
    data ... the dataset to export
    export_excel_country_code ... the countrycode to name LtgsID and NUID
    data_tags ... all values of all fields of all tags of all way elements
    
    OUTPUT
    data ... updated dataset (NUID have been added)
    (two Excel files in current directory: Power_Network (Lines) & Power_BusInfo (Nodes))  
    """

    start_time = time.time()
    print('Start exporting data to Excel files... (may take a few seconds)')

    # Read ini file and parse line properties
    config = configparser.ConfigParser()
    config.read('line_properties.ini')

    # Extract variables for 380kV and 220kV
    R_380kV = float(config['380kV']['R'])
    XL_380kV = float(config['380kV']['XL'])
    XC_380kV = float(config['380kV']['XC'])
    itherm_380kV = float(config['380kV']['itherm'])
    nominal_resistance_380kV = 380000**2/100000000

    R_220kV = float(config['220kV']['R'])
    XL_220kV = float(config['220kV']['XL'])
    XC_220kV = float(config['220kV']['XC'])
    itherm_220kV = float(config['220kV']['itherm'])
    nominal_resistance_220kV = 220000**2/100000000
    
    print(f"   ... loaded line properties for 380 kV: R={R_380kV} Ω/km, XL={XL_380kV} Ω/km, XC={XC_380kV} Ω/km, itherm={itherm_380kV} A")
    print(f"   ... loaded line properties for 220 kV: R={R_220kV} Ω/km, XL={XL_220kV} Ω/km, XC={XC_220kV} Ω/km, itherm={itherm_220kV} A")

    # Initialize and preallocate variables used in this script
    num_of_ways = len(data)

    # Assign NUID (=Node Unique ID)
    node1_data = np.zeros((num_of_ways, 4))
    node2_data = np.zeros((num_of_ways, 4))

    # Get relevant data of nodes
    node1_data[:, 0] = [way['ID_node1_final'] for way in data]
    node1_data[:, 1] = [way['voltage'] for way in data]
    node1_data[:, 2] = [way['lon1_final'] for way in data]
    node1_data[:, 3] = [way['lat1_final'] for way in data]

    node2_data[:, 0] = [way['ID_node2_final'] for way in data]
    node2_data[:, 1] = [way['voltage'] for way in data]
    node2_data[:, 2] = [way['lon2_final'] for way in data]
    node2_data[:, 3] = [way['lat2_final'] for way in data]

    # Get every unique node / voltage level combination
    nodes_unique = np.unique(np.vstack((node1_data, node2_data)), axis=0)

    # Create unique IDs for the nodes, "NUID" = Node_Unique_ID
    num_of_unique_nodes = nodes_unique.shape[0]
    counter = np.arange(1, num_of_unique_nodes + 1)
    nuid = [f'{export_excel_country_code}{str(i).zfill(5)}' for i in counter]

    # Combine the ID and the list of unique nodes into a conversion file
    nodes_conversion = np.column_stack((nuid, nodes_unique))

    # Assign NUIDs to nodes in data
    for i_nuid in range(len(nodes_unique)):
        node_org_ID = int(float(nodes_conversion[i_nuid, 1]))
        node_org_voltage = int(float(nodes_conversion[i_nuid, 2]))

        for way in data:
            if way['ID_node1_final'] == node_org_ID and way['voltage'] == node_org_voltage:
                way['node1_nuid'] = nuid[i_nuid]
            if way['ID_node2_final'] == node_org_ID and way['voltage'] == node_org_voltage:
                way['node2_nuid'] = nuid[i_nuid]
    
    # Prepare Nodes data for Excel export
    NodeID = nuid
    Country = [export_excel_country_code] * num_of_unique_nodes
    Voltage = nodes_conversion[:, 2].astype(float) / 1000
    maxVolt = [1.1] * num_of_unique_nodes  # Example constant value
    minVolt = [0.9] * num_of_unique_nodes  # Example constant value
    Bs = [0.0] * num_of_unique_nodes  # Example constant value
    Gs = [0.0] * num_of_unique_nodes  # Example constant value
    PowerFactor = [0.95] * num_of_unique_nodes  # Example constant value
    YearCom = [""] * num_of_unique_nodes
    YearDecom = [""] * num_of_unique_nodes
    lat = nodes_conversion[:, 4].astype(float)
    lon = nodes_conversion[:, 3].astype(float)

    # Create DataFrame for Nodes data with the correct format
    table_nodes = pd.DataFrame({
        'Excl.': [''] * num_of_unique_nodes,
        'NodeID': NodeID,
        'Country': Country,
        'Voltage': Voltage,
        'maxVolt': maxVolt,
        'minVolt': minVolt,
        'Bs': Bs,
        'Gs': Gs,
        'PowerFactor': PowerFactor,
        'YearCom': YearCom,
        'YearDecom': YearDecom,
        'lat': lat,
        'lon': lon
    })

    # Prepare Lines data for Excel export
    line_data = {
        'Excl.': [''] * num_of_ways,
        'fromNode': [way['node1_nuid'] for way in data],
        'toNode': [way['node2_nuid'] for way in data],
        'CloneID': [way['CloneID'] for way in data],
        'InService': [1] * num_of_ways,
        'R': [],
        'X': [],
        'Bc': [],
        'TapAngle': [0] * num_of_ways,
        'TapRatio': [1] * num_of_ways,
        'Pmax': [],
        'FixedCost': [''] * num_of_ways,
        'FxChargeRate': [''] * num_of_ways,
        'LineID': [way['LtgsID'] for way in data],
        'Voltage': [way['voltage'] for way in data],
        'LineName': [''] * num_of_ways,
        'YearCom': [''] * num_of_ways,
        'YearDecom': [''] * num_of_ways,
        'Length': [way['length'] for way in data],
        'Tags': [way['tags'] for way in data]
    }
    
    # Get information about the number of sub-conductors
    for way in data:
        way['wires'] = 1
        
        if 'wires' in way['tags']:
            if way['tags']['wires'] == 'double':
                way['wires'] = 2
            if way['tags']['wires'] == 'triple':
                way['wires'] = 3
            if way['tags']['wires'] == 'quad':
                way['wires'] = 4
                

    # Calculate R, X, Bc and Pmax based on voltage and length
    for way in data:
        length = way['length']
        if way['voltage'] == 220000:  # 220kV
            line_data['R'].append(R_220kV * length/nominal_resistance_220kV)
            line_data['X'].append(XL_220kV * length/nominal_resistance_220kV)
            line_data['Bc'].append(XC_220kV * length/nominal_resistance_220kV)
            line_data['Pmax'].append((math.sqrt(3)*way['voltage']*itherm_220kV)*math.sqrt(way['wires'])/10**6)
            # without considering sub-conductors
            #line_data['Pmax'].append((math.sqrt(3)*way['voltage']*itherm_220kV))/10**6)
        elif way['voltage'] == 380000:  # 380kV
            line_data['R'].append(R_380kV * length/nominal_resistance_380kV)
            line_data['X'].append(XL_380kV * length/nominal_resistance_380kV)
            line_data['Bc'].append(XC_380kV * length/nominal_resistance_380kV)
            line_data['Pmax'].append((math.sqrt(3)*way['voltage']*itherm_380kV)*math.sqrt(way['wires'])/10**6)
            # without considering sub-conductors
            #line_data['Pmax'].append((math.sqrt(3)*way['voltage']*itherm_380kV)/10**6)
        else:
            line_data['R'].append('')
            line_data['X'].append('')
            line_data['Bc'].append('')
            line_data['Pmax'].append('')

    # Get the information about same nodes with different voltages to add the transformers
    node_id_transformer = nodes_conversion[:, 1].astype(float)
    nuid_transformer = nodes_conversion[:, 0]
    
    # Find double occuring values
    unique, counts = np.unique(node_id_transformer, return_counts=True)
    duplicates = unique[counts > 1]

    # Add data to the transformers
    transformers = []
    for value in duplicates:
        indices = np.where(node_id_transformer == value)[0]
        node1, node2 = nuid_transformer[indices]

        transformers.append(({"Excl.": '', "fromNode": str(node1), "toNode": str(node2), "CloneID": "c1",
                     "InService": 1, "R": 0.0001, "X": 0.0123, "Bc": 0.0222, "TapAngle": 0, "TapRatio": 1,
                     "Pmax": 500, "FixedCost": '', "FxChargeRate": '' ,"LineID": '', "Voltage": '',
                     "LineName": '', "YearCom": '', "YearDecom": '', "Length": '', "Tags": "Transformer"}))

    # Add the transformer data to the line_data dict
    for row in transformers:
        line_data["Excl."].append(row["Excl."])
        line_data["fromNode"].append(row["fromNode"])
        line_data["toNode"].append(row["toNode"])
        line_data["CloneID"].append(row["CloneID"])
        line_data["InService"].append(row["InService"])
        line_data["R"].append(row["R"])
        line_data["X"].append(row["X"])
        line_data["Bc"].append(row["Bc"])
        line_data["TapAngle"].append(row["TapAngle"])
        line_data["TapRatio"].append(row["TapRatio"])
        line_data["Pmax"].append(row["Pmax"])
        line_data["FixedCost"].append(row["FixedCost"])
        line_data["FxChargeRate"].append(row["FxChargeRate"])
        line_data["LineID"].append(row["LineID"])
        line_data["Voltage"].append(row["Voltage"])
        line_data["LineName"].append(row["LineName"])
        line_data["YearCom"].append(row["YearCom"])
        line_data["YearDecom"].append(row["YearDecom"])
        line_data["Length"].append(row["Length"])
        line_data["Tags"].append(row["Tags"])


    # Create DataFrame for Lines data
    table_lines = pd.DataFrame(line_data)

    # Define folder path for saving Excel files
    folder_path = os.path.dirname(os.path.abspath(__file__)) + "/Excel-Files/"
    
    # Ensure the directory exists
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    # Function to apply formatting to the Excel files
    def apply_formatting(writer, worksheet_name, title, headers, data_frame, data_start_row):
        worksheet = writer.sheets[worksheet_name]
        workbook = writer.book

        # Define formats with centered alignment and Aptos font
        title_format = workbook.add_format({'bold': True, 'font_size': 18, 'font_color': 'white', 'font_name': 'Aptos', 'bg_color': '#008080', 'align': 'left', 'valign': 'vcenter'})
        header_format = workbook.add_format({'bold': True, 'font_size': 11, 'font_name': 'Aptos', 'bg_color': '#DAEEF3', 'align': 'center', 'valign': 'vcenter'})
        unit_format = workbook.add_format({'font_size': 11, 'font_color': 'blue', 'font_name': 'Aptos', 'bg_color': '#F2F2F2', 'align': 'center', 'valign': 'vcenter'})
        data_format = workbook.add_format({'font_name': 'Aptos', 'align': 'center', 'valign': 'vcenter'})
        green_background_format = workbook.add_format({'bg_color': '#CCFFCC', 'font_name': 'Aptos', 'align': 'center', 'valign': 'vcenter'})
        first_row_format = workbook.add_format({'bg_color': '#008080', 'font_name': 'Aptos', 'align': 'center', 'valign': 'vcenter'})
        gray_background_format = workbook.add_format({'bg_color': '#F2F2F2', 'font_name': 'Aptos', 'align': 'center', 'valign': 'vcenter'})

        # Set title in cell B1 and format the first row including B1 background color
        worksheet.write('B1', title, title_format)
        worksheet.set_row(0, 40, first_row_format)  # Set background color and height for the first row

        # Write headers in row 3 (Excel row index 3, Python index 2)
        for col_num, header in enumerate(headers):
            worksheet.write(2, col_num, header, header_format)

        # Set background color for rows 4, 5, and 6 (Excel row indices 4, 5, 6; Python indices 3, 4, 5)
        worksheet.set_row(3, None, gray_background_format)
        worksheet.set_row(4, None, gray_background_format)
        worksheet.set_row(5, None, gray_background_format)

        # Define units for each worksheet
        if worksheet_name == 'Power Network':
            units = ['', '', '', '', '[0 - 1]', '[p.u.]', '[p.u.]', '[p.u.]', '[°]', '[p.u.]', '[MW]', '[M€]', '[p.u.]', '[-]', '[V]', '[-]', '[Year]', '[Year]', '[km]']
        elif worksheet_name == 'Power BusInfo':
            units = ['', '', '', '[kV]', '[p.u.]', '[p.u.]', '[p.u.]', '[p.u.]', '[p.u.]', '[Year]', '[Year]', '°', '°']

        # Write units in row 6 (Excel row index 6, Python index 5)
        for col_num, unit in enumerate(units):
            worksheet.write(5, col_num, unit, unit_format)

        # Apply specific green background format to the specified columns in Lines and Nodes files
        if worksheet_name == 'Power Network':
            # Apply green background to columns B to M (Excel indices 1 to 12, Python indices 1 to 12)
            worksheet.conditional_format(f'B7:M{6 + len(data_frame)}', {'type': 'no_blanks', 'format': green_background_format})

            # Additionally, set the format to green for columns K to M regardless of data
            worksheet.conditional_format(f'K7:M{6 + len(data_frame)}', {'type': 'blanks', 'format': green_background_format})
            worksheet.conditional_format(f'K7:M{6 + len(data_frame)}', {'type': 'no_blanks', 'format': green_background_format})

            # Set specific width for 'R', 'XL', 'XC', and 'Length' columns
            for col in ['R', 'X', 'Bc', 'Length']:
                col_index = headers.index(col)
                worksheet.set_column(col_index, col_index, 10)  # Set width for R, XL, XC, and Length

        elif worksheet_name == 'Power BusInfo':
            # Apply green background to columns B to I (Excel indices 1 to 8, Python indices 1 to 8)
            worksheet.conditional_format(f'B7:I{6 + len(data_frame)}', {'type': 'no_blanks', 'format': green_background_format})

        # Adjust column widths based on the content
        for col_num, column in enumerate(headers):
            if column in data_frame.columns:
                # Set specific width for 'lat' and 'lon' columns
                if column in ['lat', 'lon']:
                    worksheet.set_column(col_num, col_num, 10)  # Narrower width for lat/lon
                # Already adjusted columns 'R', 'XL', 'XC', and 'Length'
                elif column in ['R', 'X', 'Bc', 'Length']:
                    continue
                else:
                    max_length = max(data_frame[column].astype(str).map(len).max(), len(column))
                    worksheet.set_column(col_num, col_num, max_length + 2)

        # Apply the centered format to all data rows
        worksheet.conditional_format(f'A7:{chr(64 + len(headers))}{6 + len(data_frame)}', {'type': 'no_blanks', 'format': data_format})

        # Hide gridlines
        worksheet.hide_gridlines(2)

    # Export Nodes DataFrame to Excel with formatting
    filename_nodes = folder_path + 'Power_BusInfo.xlsx'
    with pd.ExcelWriter(filename_nodes, engine='xlsxwriter') as writer:
        # Write DataFrame to Excel starting at row 7 (Python index 6) without headers
        table_nodes.to_excel(writer, sheet_name='Power BusInfo', index=False, startrow=6, header=False)

        # Apply formatting with appropriate headers and DataFrame
        apply_formatting(writer, 'Power BusInfo', 'Power - Bus Info', list(table_nodes.columns), table_nodes, data_start_row=6)

    # Export Lines DataFrame to Excel with formatting
    filename_lines = folder_path + 'Power_Network.xlsx'
    with pd.ExcelWriter(filename_lines, engine='xlsxwriter') as writer:
        # Write DataFrame to Excel starting at row 7 (Python index 6) without headers
        table_lines.to_excel(writer, sheet_name='Power Network', index=False, startrow=6, header=False)

        # Apply formatting with appropriate headers and DataFrame
        apply_formatting(writer, 'Power Network', 'Power - Network', list(table_lines.columns), table_lines, data_start_row=6)

    print(f'   ... finished exporting Nodes and Lines data in LEGO format in ({time.time() - start_time:.3f} seconds) \n')

    return data

def my_plot_ways_original(data, data_busbars, voltage_levels_selected, settings, data_singular_ways):
    """
    DESCRIPTION
    This function plots the original dataset as it was. Two plots will
    be generated if the flag in "bool" was set: A plot with a lon/lat
    coordinate system and a plot with an inaccurate, but more intuitive
    x/y plot in km. Since in Matlab it was a bit tricky with legends and color
    coding of same plots, a workaround with pseudo-points was necessary.
    There are a total of 12 different colors which are easy
    distinguishable. If more than 12 voltage levels will be selected,
    colors will repeat.
    
    INPUT
    data ... dataset with data to plot
    data_busbars ... the busbars which have been deleted from data
    voltage_levels_selected ... list of selected voltage levels to
                                determine color 
    settings ... boolean operator to toggle visualisations on/off
    
    OUTPUT
    (none)
    """
    if settings.plot_ways_original:
        start_time = time.time()
        print('Start plotting original ways... (takes a few seconds)')

        # Create custom 12 color qualitative Colormap for better distinctness
        # Credits: Colormap based on "paired", by www.ColorBrewer.org
        colormap = np.array([[ 51,160, 44],  [31,120,180], [177, 89, 40], [106, 61,154],
                             [255,127,  0], [178,223,138], [227, 26, 28], [255,255,153], 
                             [166,206,227], [202,178,214], [251,154,153], [253,191,111]]) / 255.0

        # Create a warning if colors of voltage levels do repeat
        if len(voltage_levels_selected) > 12:
            print('   ATTENTION!  More than 12 voltage levels are selected.\n'
                  '               Colors of voltage lines do repeat now!\n'
                  '               It is recommended to select max. 12 voltage levels.\n')

        # Extracting lat and lon data
        lat1 = [d['lat1'] for d in data]
        lat2 = [d['lat2'] for d in data]
        lon1 = [d['lon1'] for d in data]
        lon2 = [d['lon2'] for d in data]

        # Calculate midpoint to place the pseudo-points
        lat_mean = np.mean([lat1, lat2])
        lon_mean = np.mean([lon1, lon2])

        # Create figure for deg Plot
        plt.figure(figsize=(10,4.6))
        plt.title('Original ways, only selected voltages, lon/lat coordinates')
        plt.xlabel('Longitude [°]')
        plt.ylabel('Latitude [°]')
        plt.grid(True)

        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            # Cycle through the indices of 1:12 even if it exceeds 12
            i_colormap = i_vlevel % 12

            # Pick for each voltage level corresponding color
            current_color = colormap[i_colormap]

            # Plot pseudo-points at the origin in correct color order
            plt.plot(lon_mean, lat_mean, 'o-', color=current_color)

        # create legend labels
        labels = [f"{v / 1000} kV" for v in reversed(voltage_levels_selected)]

        # Create legend in correct color order
        plt.legend(labels, loc='upper left', frameon=False)

        # Set the pseudo-points invisible by overriding with a white point
        plt.plot(lon_mean, lat_mean, 'o-', color=[1, 1, 1])

        # get all coordinates of all busbars
        busbars_lon = np.vstack([np.array([d['lon1'] for d in data_busbars]), 
                                 np.array([d['lon2'] for d in data_busbars])])
        busbars_lat = np.vstack([np.array([d['lat1'] for d in data_busbars]), 
                                 np.array([d['lat2'] for d in data_busbars])])

        # Plot all busbars of current_voltage with cyan "x"
        plt.plot(busbars_lon, busbars_lat, 'cx-', linewidth=1)

        # get all coordinates of all singular ways
        singular_lon = np.vstack([np.array([d['lon1'] for d in data_singular_ways]), 
                                  np.array([d['lon2'] for d in data_singular_ways])])
        singular_lat = np.vstack([np.array([d['lat1'] for d in data_singular_ways]), 
                                  np.array([d['lat2'] for d in data_singular_ways])])

        # Plot all singular ways with black "x"
        plt.plot(singular_lon, singular_lat, 'kx-', linewidth=1)

        # Now plot the real data in correct color order, with highest vlevel
        # on top of the other voltage levels (therefore reverse for-loop)
        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            # Cycle through the indices of 1:12 even if it exceeds 12
            i_colormap = i_vlevel % 12

            # Pick for each voltage level a color
            current_color = colormap[i_colormap]

            # current voltage level in this loop:
            current_voltage = voltage_levels_selected[i_vlevel]

            # create boolean index with all wayelement in current voltage level
            b_current_voltage = [d['voltage'] == current_voltage for d in data]

            # get all ways with the current voltage level
            current_ways = [d for i, d in enumerate(data) if b_current_voltage[i]]

            # get all coordinates of current ways
            lon = np.vstack([np.array([d['lon1'] for d in current_ways]), 
                             np.array([d['lon2'] for d in current_ways])])
            lat = np.vstack([np.array([d['lat1'] for d in current_ways]), 
                             np.array([d['lat2'] for d in current_ways])])

            # Plot all ways of current_voltage in corresponding color
            plt.plot(lon, lat, '-o', color=current_color)

        plt.show()  # Display the first plot
        plt.close()  # Close the first plot

        # Create figure for X/Y km Plot
        plt.figure(figsize=(10,4.6))
        plt.title('Original ways, only selected voltages, x/y coordinates')
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        plt.grid(True)

        # Extracting x and y data
        x1 = [d['x1'] for d in data]
        x2 = [d['x2'] for d in data]
        y1 = [d['y1'] for d in data]
        y2 = [d['y2'] for d in data]

        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            # Cycle through the indices of 1:12 even if it exceeds 12
            i_colormap = i_vlevel % 12

            # Pick for each voltage level corresponding color
            current_color = colormap[i_colormap]

            # Plot pseudo-points at the origin in correct color order
            plt.plot([0, 0], [0, 0], 'o-', color=current_color)

        # create legend labels
        labels = [f"{v / 1000} kV" for v in reversed(voltage_levels_selected)]

        # Create legend in correct color order
        plt.legend(labels, loc='upper left', frameon=False)

        # Set the pseudo-points invisible by overriding with a white point
        plt.plot([0, 0], [0, 0], 'o-', color=[1, 1, 1])

        # get all coordinates of all busbars
        busbars_x = np.vstack([np.array([d['x1'] for d in data_busbars]), 
                               np.array([d['x2'] for d in data_busbars])])
        busbars_y = np.vstack([np.array([d['y1'] for d in data_busbars]), 
                               np.array([d['y2'] for d in data_busbars])])

        # Plot all busbars/bays of current_voltage in cyan
        plt.plot(busbars_x, busbars_y, 'cx-', linewidth=1)

        # get all coordinates of all singular ways
        singular_x = np.vstack([np.array([d['x1'] for d in data_singular_ways]), 
                                np.array([d['x2'] for d in data_singular_ways])])
        singular_y = np.vstack([np.array([d['y1'] for d in data_singular_ways]), 
                                np.array([d['y2'] for d in data_singular_ways])])

        # Plot all singular ways with black "x"
        plt.plot(singular_x, singular_y, 'kx-', linewidth=1)

        # Now plot the real data in correct color order, with highest vlevel
        # on top of the other voltage levels (therefore reverse for-loop)
        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            # Cycle through the indices of 1:12 even if it exceeds 12
            i_colormap = i_vlevel % 12

            # Pick for each voltage level a color
            current_color = colormap[i_colormap]

            # current voltage level in this loop:
            current_voltage = voltage_levels_selected[i_vlevel]

            # create boolean index with all wayelement in current voltage level
            b_current_voltage = [d['voltage'] == current_voltage for d in data]

            # get all ways with the current voltage level
            current_ways = [d for i, d in enumerate(data) if b_current_voltage[i]]

            # get all coordinates of current ways
            x = np.vstack([np.array([d['x1'] for d in current_ways]), 
                           np.array([d['x2'] for d in current_ways])])
            y = np.vstack([np.array([d['y1'] for d in current_ways]), 
                           np.array([d['y2'] for d in current_ways])])

            # Plot all ways of current_voltage in corresponding color
            plt.plot(x, y, '-o', color=current_color)

        plt.show()  # Display the second plot

        print(f'   ... finished! ({time.time() - start_time:.3f} seconds)\n')


def my_plot_ways_grouping(data, data_busbars, grouped_xy_coordinates, neighbourhood_threshold, settings):
    """
    DESCRIPTION
    This function will plot the transition while grouping endnodes. In
    grey with dotted lines the original dataset will be plotted, all
    endnodes which will be grouped together, so which are stacked or in a
    neighbourhood, will be plotted in a different color (be aware that by
    accident neighbouring neighbourhood-groups can occasionally have the
    same colors!). Over all grouped endnodes a circle with the threshold
    radius will be plotted, this is very helpful to determine the correct
    value for the threshold. If the plot reveals that obviously
    neighbouring groups won't be grouped correctly, it is useful to
    increase the threshold radius, the opposite is true if endnodes,
    which should not be grouped together, will be grouped.
    
    INPUT
    data ... dataset with data to plot
    data_busbars ... the busbars which have been deleted from data
    grouped_xy_coordinates ... all x/y coordinates of a group
    neighbourhood_threshold ... the radius of grouping
    settings ... boolean operator to toggle visualisations on/off
    
    OUTPUT
    (none)
    """
    if settings.plot_ways_grouping:
        if data is None:
            print('No data provided for plotting.')
            return
        
        start_time = time.time()
        print('Start plotting all grouped endnodes... (takes a few seconds)')
        
        # Start figure
        plt.figure(figsize=(10,4.6))
        plt.title('Original and final ways with grouping-circles')
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        plt.grid(True)

        # Filter out None values from data
        data = [way for way in data if way is not None]
        
        if not data:
            print('No valid data to plot.')
            return
        
        # Plot all ways dashed with all original endnodes in light grey
        try:
            x = np.vstack(([way['x1'] for way in data], [way['x2'] for way in data]))
            y = np.vstack(([way['y1'] for way in data], [way['y2'] for way in data]))
        except KeyError as e:
            print(f'Missing key in data: {e}')
            return

        plt.plot(x, y, 'o--', color=[0.6, 0.6, 0.6])

        # get all coordinates of all busbars
        busbars_lon = np.vstack([np.array([busbar['lon1'] for busbar in data_busbars]), 
                                 np.array([busbar['lon2'] for busbar in data_busbars])])
        busbars_lat = np.vstack([np.array([busbar['lat1'] for busbar in data_busbars]), 
                                 np.array([busbar['lat2'] for busbar in data_busbars])])

        # Plot all busbars of current_voltage with black "x" and crossed lines
        plt.plot(busbars_lon, busbars_lat, 'o--', color=[0.6, 0.6, 0.6])

        # Plot circles around each grouped endpoint
        origin_circles = np.reshape([coord for group in grouped_xy_coordinates for coord in group if coord is not None], (-1, 2))
        radii = neighbourhood_threshold * np.ones(origin_circles.shape[0])
        for circle in origin_circles:
            circle_plot = plt.Circle(circle, neighbourhood_threshold, color='b', fill=False, linestyle=':')
            plt.gca().add_patch(circle_plot)

        # Plot the new ways
        try:
            x_final = np.vstack(([way['x1_final'] for way in data], [way['x2_final'] for way in data]))
            y_final = np.vstack(([way['y1_final'] for way in data], [way['y2_final'] for way in data]))
        except KeyError as e:
            print(f'Missing key in data: {e}')
            return

        plt.plot(x_final, y_final, 'k-o')

        # Plot all new grouped endpoints in pink
        x_grouped = np.vstack(([way['x1_grouped'] for way in data], [way['x2_grouped'] for way in data]))
        y_grouped = np.vstack(([way['y1_grouped'] for way in data], [way['y2_grouped'] for way in data]))

        plt.plot(x_grouped, y_grouped, '.m', markersize=15)

        # Plot all groups of combined endpoints in a different color
        for i_group, group_xy in enumerate(grouped_xy_coordinates):
            group_xy = [coord for coord in group_xy if coord is not None]
            group_xy = np.reshape(group_xy, (-1, 2))
            plt.plot(group_xy[:, 0], group_xy[:, 1], '*')

        plt.show()
        print(f'   ... finished! ({time.time() - start_time:.3f} seconds)')


def my_plot_ways_final(data, voltage_levels_selected, settings):
    """
    DESCRIPTION
    This function plots the final dataset as it will be exported. Two plots 
    will be generated if the flag in "settings" was set: A plot with a lon/lat
    coordinate system and a plot with an inaccurate, but more intuitive
    x/y plot in km. Since Matplotlib is a bit tricky with legends and color
    coding of same plots, a workaround with pseudo-points is necessary.
    There are a total of 12 different colors which are easy
    distinguishable. If more than 12 voltage levels will be selected,
    colors will repeat.
    
    INPUT
    data ... dataset with data to plot
    voltage_levels_selected ... list of selected voltage levels to
                                determine color 
    settings ... boolean operator to toggle visualisations on/off
    
    OUTPUT
    (none)
    """
    if settings.plot_ways_final:
        if not data:
            print('No data provided for plotting.')
            return
        
        start_time = time.time()
        print('Start plotting final ways... (takes a few seconds)')

        # Create custom 12 color qualitative Colormap for better distinctness
        colormap = np.array([
            [51, 160, 44], [31, 120, 180], [177, 89, 40], [106, 61, 154],
            [255, 127, 0], [178, 223, 138], [227, 26, 28], [255, 255, 153], 
            [166, 206, 227], [202, 178, 214], [251, 154, 153], [253, 191, 111]
        ]) / 255.0

        # Create a warning if colors of voltage levels do repeat
        if len(voltage_levels_selected) > 12:
            print('   ATTENTION! More than 12 voltage levels are selected.')
            print('               Colors of voltage lines do repeat now!')
            print('               It is recommended to select max. 12 voltage levels.')

        # Calculate midpoint to place the pseudo-points
        lat_mean = np.mean([item['lat1_final'] for item in data] + [item['lat2_final'] for item in data])
        lon_mean = np.mean([item['lon1_final'] for item in data] + [item['lon2_final'] for item in data])

        # Create figure for degree (lon/lat coordinates)
        plt.figure(figsize=(10,4.6))
        plt.title('Final ways as exported, lon/lat coordinates')
        plt.xlabel('Longitude [°]')
        plt.ylabel('Latitude [°]')
        plt.grid(True)

        # Plot pseudo-points
        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]

            # Plot pseudo-points at the midpoint in correct color order
            plt.plot(lon_mean, lat_mean, 'o-', color=current_color)

        # Create legend labels
        labels = [f"{vl / 1000} kV" for vl in reversed(voltage_levels_selected)]

        # Create legend in correct color order
        plt.legend(labels, loc='upper left', frameon=False)

        # Set the pseudo-points invisible by overriding with a white point
        plt.plot(lon_mean, lat_mean, 'o-', color=[1, 1, 1])

        # Now plot the real data in correct color order
        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]
            current_voltage = voltage_levels_selected[i_vlevel]

            # create boolean index with all way elements in current voltage level
            b_current_voltage = [item for item in data if item['voltage'] == current_voltage]

            # get all coordinates of current ways
            lon = np.array([[item['lon1_final'], item['lon2_final']] for item in b_current_voltage]).T
            lat = np.array([[item['lat1_final'], item['lat2_final']] for item in b_current_voltage]).T

            # Plot all ways of current_voltage in corresponding color
            plt.plot(lon, lat, '-o', color=current_color)

        # Show the figure
        plt.show()

        # Create figure for X/Y km coordinates
        plt.figure(figsize=(10,4.6))
        plt.title('Final ways as exported, x/y coordinates')
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        plt.grid(True)

        # Plot pseudo-points
        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]

            # Plot pseudo-points at the origin in correct color order
            plt.plot(0, 0, 'o-', color=current_color)

        # Create legend in correct color order
        plt.legend(labels, loc='upper left', frameon=False)

        # Set the pseudo-points invisible by overriding with a white point
        plt.plot(0, 0, 'o-', color=[1, 1, 1])

        # Now plot the real data in correct color order
        for i_vlevel in range(len(voltage_levels_selected) - 1, -1, -1):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]
            current_voltage = voltage_levels_selected[i_vlevel]

            # create boolean index with all way elements in current voltage level
            b_current_voltage = [item for item in data if item['voltage'] == current_voltage]

            # get all coordinates of current ways
            x = np.array([[item['x1_final'], item['x2_final']] for item in b_current_voltage]).T
            y = np.array([[item['y1_final'], item['y2_final']] for item in b_current_voltage]).T

            # Plot all ways of current_voltage in corresponding color
            plt.plot(x, y, '-o', color=current_color)

        # Show the figure
        plt.show()

        print(f'   ... finished! ({time.time() - start_time:.3f} seconds)')
            
def main_program():
    overallruntime_start = time.time()
    
    # Print welcome message and a few settings
    if settings.calculate_real_line_length:
        string_real_length = 'Real line length WILL be calculated'
    else:
        string_real_length = 'Real line length NOT be calculated'
    
    print(f'''WELCOME to GridTool!
(C) created by Lukas Frauenlob and Robert Gaugl, IEE, TU Graz
    Updated by Juergen Reiter, TU Graz

--- Info ---
   ... to restart data import, please delete variable "data_raw". 
   ... to restart voltage level selection, delete "voltage_levels_selected". 
   ... please check if visualisations are toggled on/off for either 
       performance improvements or additional information!

--- Settings --- 
   
   ... Neighbouring (=grouping circle) threshold: {neighbourhood_threshold:5.2f} km 
   ... {string_real_length} 
   ... Line length slack compensation factor: {way_length_multiplier:3.2f}
''')
    #... Country code for Excel output: "{export_excel_country_code}"
    
    # Import Data
    print('--- Import data (Step 1/6) ---')
    
    # If data wasn't imported yet, open UI, select json.file and import it
    if 'data_raw' not in locals():
        data_raw, file_name, file_path = my_import_json()
        
        # When importing new data (possibly from another country), delete old voltage_levels_selected to force new vlevel selection 
        if 'voltage_levels_selected' in locals():
            del voltage_levels_selected

    # Separate all 'node' and 'way' elements to separate variables and add UID
    data_nodes_all, data_ways_all = my_separate_raw_data_add_UID(data_raw)

    # Add the lat/lon & X/Y coordinates and way lengths to all ways
    data_ways_all, degrees_to_km_conversion, mean_country_lat, mean_country_lon = my_add_coordinates(data_ways_all, data_nodes_all)
    
    # Select voltage levels
    print('\n--- Select voltage levels (Step 2/6) ---')

    # Count the number of lines with a specific voltage level, display and add it 
    data_ways_all, voltage_levels_sorted = my_count_voltage_levels(data_ways_all)
    
    #voltage_levels_selected = [220000.0, 380000.0]
    # Open a dialog to ask the user to select voltage levels 
    if 'voltage_levels_selected' not in locals():
        voltage_levels_selected = my_ask_voltage_levels(voltage_levels_sorted)

    # Save all ways which match selected voltage levels
    data_ways_selected = my_select_ways(data_ways_all, voltage_levels_selected)
    
    # Analyse data
    print('\n--- Analyse data (Step 3/6) ---')

    # Find all ways with type busbars, extract them and delete them
    data_ways_selected, data_busbars = my_delete_busbars(data_ways_selected, settings, busbar_max_length)

    # Detect all possible railroad lines
    data_ways_selected, railroad_candidates = my_count_possible_railroad(data_ways_selected)

    # Detect all possible DC lines
    data_ways_selected, dc_candidates = my_count_possible_dc(data_ways_selected)

    # Count how many cables a way has (needed to double or triple a way), add flags
    data_ways_selected = my_count_cables(data_ways_selected)

    # Group nodes
    print('\n--- Group nodes (Step 4/6) ---')

    # Calculate distances between all endpoints
    distances_between_nodes = my_calc_distances_between_endpoints(data_ways_selected, degrees_to_km_conversion, settings)

    # Calculate all stacked nodes
    data_ways_selected, nodes_stacked_pairs = my_calc_stacked_endnodes(data_ways_selected, distances_between_nodes, settings)

    # Calculate neighbouring nodes
    data_ways_selected, nodes_neighbouring_pairs = my_calc_neighbouring_endnodes(data_ways_selected, distances_between_nodes, neighbourhood_threshold, settings)
    
    # Group stacked nodes
    nodes_stacked_grouped = my_group_nodes(nodes_stacked_pairs)

    # Group neighbouring nodes                               
    nodes_neighbouring_grouped = my_group_nodes(nodes_neighbouring_pairs)

    # Add coordinates of stacked endnodes
    data_ways_selected = my_group_stacked_endnodes(data_ways_selected, nodes_stacked_grouped)
    
    # Add coordinates of neighbouring endnodes
    data_ways_selected, grouped_xy_coordinates = my_group_neighbouring_endnodes(data_ways_selected, nodes_neighbouring_grouped, degrees_to_km_conversion)
    
    # Add final coordinates, hence select from original or grouped coordinates                         
    data_ways_selected = my_add_final_coordinates(data_ways_selected)

    # Export   
    print('\n--- Export (Step 5/6) ---')

    # Delete ways which have identical endpoints
    data_ways_selected, data_singular_ways = my_delete_singular_ways(data_ways_selected)

    # Calculate the real length of a line
    data_ways_selected, data_ways_selected_lengths = my_calc_real_lengths(data_ways_selected, data_ways_all, data_nodes_all, settings)

    # Copy all tags of all ways into a separate variable
    data_ways_selected_tags = my_get_tags(data_ways_selected)

    # Get the country code from the mean lon and lat coordinates of the data
    export_excel_country_code = my_get_country_code_from_coordinates(mean_country_lon, mean_country_lat)

    # Remove unwanted duplicates
    data_ways_selected = remove_duplicates(data_ways_selected)
    
    # Add LtgsID and duplicate ways if necessary
    data_ways_selected = my_add_LtgsID_clone_ways(data_ways_selected, export_excel_country_code)
    
    # Export data to excel files, add NUID
    if settings.lego_export:
        data_ways_selected = my_export_excel_lego(data_ways_selected, export_excel_country_code, data_ways_selected_tags, way_length_multiplier)
    else:
        data_ways_selected = my_export_excel(data_ways_selected, export_excel_country_code, data_ways_selected_tags, way_length_multiplier)

    #Visualisations
    print('\n--- Visualisations (Step 6/6) ---')

    # Plot original ways
    my_plot_ways_original(data_ways_selected, data_busbars, voltage_levels_selected, settings, data_singular_ways)

    # Plot ways while grouping endnodes
    my_plot_ways_grouping(data_ways_selected, data_busbars, grouped_xy_coordinates, neighbourhood_threshold, settings)

    # Plot final ways
    my_plot_ways_final(data_ways_selected, voltage_levels_selected, settings)

    
    print(f'\n\nOverall runtime of program: {time.time() - overallruntime_start:.3f} seconds. \nCONVERSION COMPLETED \n \n')

if __name__ == "__main__":
    main_program()
