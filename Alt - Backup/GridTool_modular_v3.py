# %% Initialization and Settings

# Initialization
import time
import matplotlib.pyplot as plt
import numpy as np
import json
import tkinter as tk
from tkinter import filedialog
import pandas as pd
from matplotlib.patches import Circle
from datetime import datetime
import xlsxwriter

# Clear variables
# In Python, we typically don't need to clear variables manually

# Start overall runtime timer
overallruntime_start = time.time()

# Settings
# Two character country code, according to ISO-3166-1, of current country
export_excel_country_code = "AT"

# Set neighbourhood threshold radius to determine, how close endnodes have 
# to be together to get grouped
neighbourhood_threshold = 0.5

# Max. length of a line which can be a type 'busbar', in km
busbar_max_length = 1

# Multiplier factor for the exported length of line (slack compensation)
way_length_multiplier = 1.2

# Display all numbers (up to 15 digits) in console without scientific notation
np.set_printoptions(precision=15, suppress=True)

# Calculating real line length?
# Set if the real line length should be calculated (may take some minutes) or
# the beeline ("Luftlinie") should be used
calculate_real_line_length = True

# If real line length gets visualized, set threshold to plot only ways which
# have a difference in beeline-length/real-length of at least x% (standard: 5%)
beeline_visu_treshold_diff_percent = 5

# If real line length gets visualized, set threshold to plot only ways which
# have a difference in beeline-length/real-length of at least xkm (standard: 0.5km)
beeline_visu_treshold_diff_absolut = 0.5

# Toggle visualizations on/off

# Recommended visualizations
# Visualize all selected ways, hence the original dataset 
plot_ways_original = False

# Visualize all selected ways, while they are being grouped. This plot
# includes the original and the new ways, including the threshold-circles
plot_ways_grouping = False

# Visualize all selected ways on map, final dataset with endnodes grouped
plot_ways_final = False

# Visualize distances between all endnodes to easier set neighbourhood_threshold
histogram_distances_between_endpoints = False

# Visualize Comparison between real line course and beeline
plot_comparison_real_beeline = False

# Optional visualizations, for debugging purposes and in-depth-research
# Visualize length of busbars to set busbar_max_length
histogram_length_busbars = False

# Visualize how many endnodes are stacked on top of each other
histogram_stacked_endnodes = False

# Visualize all stacked endnodes on map
plot_stacked_endnodes = False

# Visualize how many neighboring endnodes are grouped together 
histogram_neighbouring_endnodes = False

# Visualize all neighboring endnodes on map
plot_neighbouring_endnodes = False

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
    
    start_time = time.time()

    # Print file path and filename to console
    print(f'   ... file path: {file_path} \n   ... file name: {file_name}')
            
    # Import and decode selected .json file into workspace
    with open(file_path, 'r') as f:
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
    return data, degrees_to_km_conversion

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
            print(f'   ATTENTION! Way element UID {way["UID"]} does not contain a field "voltage". This way wont be selected.')
            continue

        voltage_levels = []

        voltage_levels = list(map(float, way['tags']['voltage'].split(';')))
        
        if any(np.isnan(voltage_levels)):
            print(f'   ATTENTION! UNKNOWN voltage level ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way wont be selected.')
            continue
        
        if len(voltage_levels) == 1:
            way['voltage'] = voltage_levels[0]
            way['vlevels'] = 1
        elif len(voltage_levels) == 2:
            way['voltage'] = None
            way['vlevels'] = 2
            print(f'   ATTENTION! Two voltage levels ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way will be duplicated.')
        elif len(voltage_levels) == 3:
            way['voltage'] = None
            way['vlevels'] = 3
            print(f'   ATTENTION! Three voltage levels ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way will be tripled.')
        else:
            way['voltage'] = None
            way['vlevels'] = None
            print(f'   ATTENTION! Unknown voltage levels ("{way["tags"]["voltage"]}") in UID {way["UID"]}. This way wont be selected.')
    
    print('\n   ... start cloning lines with multiple voltage levels... (may take a few seconds)')
    
    num_of_cloned_ways = 0
    iterations_to_skip = 0
    
    i = 0
    while i < len(data):
        if iterations_to_skip > 0:
            iterations_to_skip -= 1
            i += 1
            continue
        
        if data[i]['vlevels'] == 2:
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
    
    voltage_levels = [way['voltage'] for way in data if way['voltage'] is not None]
    voltage_levels_unique, voltage_levels_occurance = np.unique(voltage_levels, return_counts=True)
    
    voltage_levels_sorted = sorted(zip(voltage_levels_unique, voltage_levels_occurance), key=lambda x: x[0], reverse=True)
    
    print('\n')
    print(f"{'voltage_level':>15} {'number_of_ways':>15}")
    for level, count in voltage_levels_sorted:
        print(f"{level:>15} {count:>15}")
    
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
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()

    voltage_levels_str = [str(v) for v in voltage_levels_sorted]
    voltage_levels_selected_str = simpledialog.askstring("Voltage Level Selection", "Please select one or multiple voltage levels (separated by commas):", initialvalue=", ".join(voltage_levels_str))

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
    import time
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
        import matplotlib.pyplot as plt
        plt.figure()
        plt.hist(lengths_of_busbars, bins=200)
        plt.title('Lengths of busbars/bays below busbar-max-length-threshold')
        plt.xlabel('Length [km]')
        plt.ylabel('Number of busbars with that length')
        plt.show()
    
    print(f'   ... {i_busbars_bays} busbars have been deleted\n   ... finished! ({time.time() - start_time:.3f} seconds)')
    
    return data, data_busbars

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
        way['dc_candidate'] = False

        if 'frequency' in way['tags'] and str(way['tags']['frequency']) == '0':
            way['dc_candidate'] = True
            dc_candidates.append({'UID': way['UID'], 'voltage_level': way['voltage'], 'reason': 'tag "frequency" has value "0"'})
        
        if 'name' in way['tags'] and 'dc' in way['tags']['name'].lower():
            way['dc_candidate'] = True
            dc_candidates.append({'UID': way['UID'], 'voltage_level': way['voltage'], 'reason': 'tag "name" contains "DC"'})
        
        if 'cables' in way['tags'] and str(way['tags']['cables']) == '1':
            way['dc_candidate'] = True
            dc_candidates.append({'UID': way['UID'], 'voltage_level': way['voltage'], 'reason': 'tag "cables" has value "1"'})

    if not dc_candidates:
        dc_candidates.append({'UID': 'No possible DC candidate in all ways of those selected voltage levels found!'})
        print('   ... no potentially DC lines found.')
    else:
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
                num_of_cables = int(way['tags']['cables'])
            except ValueError:
                print(f'   ATTENTION! Unknown cable number ("{way["tags"]["cables"]}") in UID {way["UID"]}. This way wont be cloned automatically.')
                continue

            way['cables'] = num_of_cables
            cables_per_way.append({'UID': way['UID'], 'num_of_cables': num_of_cables})

            if num_of_cables == 6:
                way['systems'] = 2
            elif num_of_cables == 9:
                way['systems'] = 3
            elif num_of_cables == 12:
                way['systems'] = 4
            else:
                way['systems'] = None
        else:
            way['systems'] = None

    if not cables_per_way:
        print('   ... the ways in this voltage level selection don\'t provide information about number of cables...')
        cables_per_way.append({'UID': 'No information about number of cables provided in this selection.'})
    else:
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

def my_calc_distances_between_endpoints(data, degrees_to_km_conversion, settings):
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
    neighboring threshold value.
    
    INPUT
    data ... dataset of all selected ways
    degrees_to_km_conversion ... conversion factors for longitude and latitude to km
    settings ... settings object with plot options
    
    OUTPUT
    M ... matrix with all distances between all endpoints
    """
    start_time = time.time()
    print('Start calculating distances between all endpoints... (takes a few seconds)')
    
    num_ways = len(data)
    M = np.full((num_ways * 2, num_ways * 2), np.nan)
    
    km_per_lon_deg = degrees_to_km_conversion[0]
    km_per_lat_deg = degrees_to_km_conversion[1]
    
    all_lon1 = np.array([way['lon1'] for way in data])
    all_lon2 = np.array([way['lon2'] for way in data])
    all_lat1 = np.array([way['lat1'] for way in data])
    all_lat2 = np.array([way['lat2'] for way in data])
    
    for i_row in range(num_ways):
        data_column = np.array([[data[i_row]['lon1'], data[i_row]['lat1']],
                                [data[i_row]['lon2'], data[i_row]['lat2']]])
        
        if i_row < num_ways - 1:
            remaining_lon1 = all_lon1[i_row + 1:]
            remaining_lon2 = all_lon2[i_row + 1:]
            remaining_lat1 = all_lat1[i_row + 1:]
            remaining_lat2 = all_lat2[i_row + 1:]
        
            data_row = np.zeros((2, len(remaining_lon1) * 2))
            data_row[0, 0::2] = remaining_lon1
            data_row[0, 1::2] = remaining_lon2
            data_row[1, 0::2] = remaining_lat1
            data_row[1, 1::2] = remaining_lat2
        
            lon_deltas_to_lon1_deg = data_column[0, 0] - data_row[0, 0::2]
            lon_deltas_to_lon2_deg = data_column[1, 0] - data_row[0, 1::2]
            lat_deltas_to_lat1_deg = data_column[0, 1] - data_row[1, 0::2]
            lat_deltas_to_lat2_deg = data_column[1, 1] - data_row[1, 1::2]
        
            lon_deltas_to_lon1_km = lon_deltas_to_lon1_deg * km_per_lon_deg
            lon_deltas_to_lon2_km = lon_deltas_to_lon2_deg * km_per_lon_deg
            lat_deltas_to_lat1_km = lat_deltas_to_lat1_deg * km_per_lat_deg
            lat_deltas_to_lat2_km = lat_deltas_to_lat2_deg * km_per_lat_deg
        
            M_new_row = np.full((2, len(remaining_lon1) * 2), np.nan)
            M_new_row[0, 0::2] = np.sqrt(lon_deltas_to_lon1_km**2 + lat_deltas_to_lat1_km**2)
            M_new_row[1, 0::2] = np.sqrt(lon_deltas_to_lon2_km**2 + lat_deltas_to_lat2_km**2)
        
            M[2 * i_row:2 * i_row + 2, 2 * (i_row + 1):2 * (i_row + 1) + M_new_row.shape[1]] = M_new_row
        
        M[2 * i_row, 2 * i_row] = -1
        M[2 * i_row + 1, 2 * i_row + 1] = -1

    if settings.histogram_distances_between_endpoints:
        print('   ... start visualizing all distances in a histogram ...')
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 15))
        
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
    
    print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
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
    settings ... settings object with plot options
    
    OUTPUT
    data ... updated dataset, new flag: endnode1/2_stacked
    nodes_stacked_pairs ... a raw list of all pairs of stacked endnodes
    """
    start_time = time.time()
    print('Start finding all stacked endnodes...')
    
    # Initialize 'node1_stacked' and 'node2_stacked' attributes
    for way in data:
        way['node1_stacked'] = False
        way['node2_stacked'] = False
    
    # Create boolean logical index of all distance combinations which equal 0
    b_dist_is_zero = (distances == 0)
    
    # if no distance element has value 0, cancel that function since no two
    # endpoints are stacked
    if not np.any(b_dist_is_zero):
        print('   ... no endnode is stacked!')
        nodes_stacked_pairs = []
        print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
        return data, nodes_stacked_pairs
    
    # Get the indices of this boolean matrix, hence the row/column IDs
    stacked_indices = np.argwhere(b_dist_is_zero)
    
    # Combine the row(y)- and column(x)-indices in one list and sort them
    stacked_indices_combined = np.sort(stacked_indices.flatten())
    
    # Remove duplicates: extract unique ids and calculate their occurrences
    unique_indices, unique_counts = np.unique(stacked_indices_combined, return_counts=True)
    
    print('   ... %d endnodes are stacked!' % len(unique_indices))
    
    # Create a list of unique stacked nodes
    nodes_stacked = [{'index': idx, 'way_ID': idx // 2, 'endnode1': (idx % 2 == 0)} for idx in unique_indices]
    
    # Group nodes into pairs
    nodes_stacked_pairs = [(stacked_indices[i, 0], stacked_indices[i, 1]) for i in range(len(stacked_indices))]
    
    # Add stacked information to dataset
    for node in nodes_stacked:
        way_ID = node['way_ID']
        endnode1 = node['endnode1']
        
        if endnode1:
            data[way_ID]['node1_stacked'] = True
        else:
            data[way_ID]['node2_stacked'] = True
    
    print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
    
    # Visualize this stacked data
    if settings.plot_stacked_endnodes:
        import matplotlib.pyplot as plt
        
        print('Start visualizing all stacked endnodes (takes a few seconds)...')
        
        # Extract all nodes
        x = np.array([[way['x1'], way['x2']] for way in data])
        y = np.array([[way['y1'], way['y2']] for way in data])
        
        # Extract node1 if it is stacked, else ignore it
        x_node1_stacked = x[:, 0][[way['node1_stacked'] for way in data]]
        y_node1_stacked = y[:, 0][[way['node1_stacked'] for way in data]]
        
        # Extract node2 if it is stacked, else ignore it
        x_node2_stacked = x[:, 1][[way['node2_stacked'] for way in data]]
        y_node2_stacked = y[:, 1][[way['node2_stacked'] for way in data]]
        
        # Plot all nodes, highlight node1 and node2 if stacked
        plt.figure()
        plt.title('All ways with endnodes STACKED on XY-Map')
        plt.grid(True)
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        
        for way in data:
            plt.plot([way['x1'], way['x2']], [way['y1'], way['y2']], 'ok-')
        
        plt.plot(x_node1_stacked, y_node1_stacked, 'xr')
        plt.plot(x_node2_stacked, y_node2_stacked, '+b')
        
        plt.show()
        
        print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
    
    # Plot histogram of how many endnodes are stacked
    if settings.histogram_stacked_endnodes:
        import matplotlib.pyplot as plt
        
        plt.figure()
        plt.hist(unique_counts, bins=np.max(unique_counts))
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
    
    # Get the indices of this boolean matrix, hence the ids of elements
    neighbour_indices = np.argwhere(b_dist_neighbourhood)
    
    # Combine the row(y)- and column(x)-indices in one list and sort them
    neighbour_indices_combined = np.sort(neighbour_indices.flatten())
    
    # Remove duplicates: extract unique ids and calculate their occurrences
    unique_indices, unique_counts = np.unique(neighbour_indices_combined, return_counts=True)
    
    print('   ... %d endnodes are in same neighbourhood!' % len(unique_indices))
    
    # Create a list of unique neighbouring nodes
    nodes_neighbouring = [{'index': idx, 'way_ID': idx // 2, 'endnode1': (idx % 2 == 0)} for idx in unique_indices]
    
    # Group nodes into pairs
    nodes_neighbouring_pairs = [(neighbour_indices[i, 0], neighbour_indices[i, 1]) for i in range(len(neighbour_indices))]
    
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
        import matplotlib.pyplot as plt
        
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
        plt.figure()
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
        import matplotlib.pyplot as plt
        
        plt.figure()
        plt.hist(unique_counts, bins=np.max(unique_counts))
        plt.title('Neighbouring endnodes: How many will be in one group?')
        plt.xlabel('Number of nodes which will be grouped together')
        plt.ylabel('Number of different positions this occurs in')
        plt.show()
    
    return data, nodes_neighbouring_pairs


def my_group_nodes(pairs_input):
    """
    DESCRIPTION
    This function takes as input a list of pairs (stacked_pairs or
    neighbouring_pairs) to group them. This function checks all cases,
    hence creates new groups, adds elements to an existing group and even
    concatenate groups.

    INPUT
    pairs_input ... list of pairs

    OUTPUT
    list ... a list of groups made out of the pairs from pairs_input
    """
    start_time = time.time()
    print(f'Start grouping all pairs from "{pairs_input}" (may take a few seconds)...')

    list_groups = []

    pairs_sorted_horizontally = np.sort(pairs_input, axis=1)
    pairs_sorted_vertically = pairs_sorted_horizontally[np.argsort(pairs_sorted_horizontally[:, 0])]

    for partner1, partner2 in pairs_sorted_vertically:
        row_partner1 = next((i for i, group in enumerate(list_groups) if partner1 in group), None)
        row_partner2 = next((i for i, group in enumerate(list_groups) if partner2 in group), None)

        if row_partner1 is not None:
            if row_partner2 is not None:
                if row_partner1 != row_partner2:
                    list_groups[row_partner1].update(list_groups[row_partner2])
                    list_groups.pop(row_partner2)
            else:
                list_groups[row_partner1].add(partner2)
        elif row_partner2 is not None:
            list_groups[row_partner2].add(partner1)
        else:
            list_groups.append({partner1, partner2})

    list_groups = [sorted(list(group)) for group in list_groups]

    print(f'   ... {sum(len(group) for group in list_groups)} nodes will be grouped together in {len(list_groups)} grouped nodes,')
    print(f'       with an average of {sum(len(group) for group in list_groups) / len(list_groups):.2f} nodes per grouped node.')
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')

    return list_groups

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
    data ... updated dataset where all stacked nodes have the same group node id
    """
    start_time = time.time()
    print('Start adding coordinates of stacked groups...')

    for group in nodes_stacked_grouped:
        grouped_node_ID = group[0]
        i_way_ID = (grouped_node_ID + 1) // 2 - 1
        b_node1 = grouped_node_ID % 2

        if b_node1:
            grouped_lon, grouped_lat, grouped_x, grouped_y = data[i_way_ID]['lon1'], data[i_way_ID]['lat1'], data[i_way_ID]['x1'], data[i_way_ID]['y1']
        else:
            grouped_lon, grouped_lat, grouped_x, grouped_y = data[i_way_ID]['lon2'], data[i_way_ID]['lat2'], data[i_way_ID]['x2'], data[i_way_ID]['y2']

        for node_ID in group:
            i_way_ID = (node_ID + 1) // 2 - 1
            b_node1 = node_ID % 2

            if b_node1:
                data[i_way_ID]['ID_node1_grouped'] = grouped_node_ID
                data[i_way_ID]['lon1_grouped'] = grouped_lon
                data[i_way_ID]['lat1_grouped'] = grouped_lat
                data[i_way_ID]['x1_grouped'] = grouped_x
                data[i_way_ID]['y1_grouped'] = grouped_y
            else:
                data[i_way_ID]['ID_node2_grouped'] = grouped_node_ID
                data[i_way_ID]['lon2_grouped'] = grouped_lon
                data[i_way_ID]['lat2_grouped'] = grouped_lat
                data[i_way_ID]['x2_grouped'] = grouped_x
                data[i_way_ID]['y2_grouped'] = grouped_y

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data

def my_group_neighbouring_endnodes(data, nodes_neighbouring_grouped, degrees_to_km_conversion):
    """
    DESCRIPTION
    This function extracts all lon/lat coordinates of all members for every
    neighbouring group, then calculates the mean lon/lat value and copies
    it to every group member. Then the x/y values will newly be
    calculated and too added.
    
    INPUT
    data ... original input dataset
    nodes_neighbouring_grouped ... list with nodes grouped
    degrees_to_km_conversion ... conversion data to calculate x/y coordinates
    
    OUTPUT
    data ... updated dataset with grouped fields
    grouped_xy_coordinates ... list of x/y coordinates of grouped nodes,
                               this will be used in a plot later
    """
    start_time = time.time()
    print('Start adding grouping neighbours...')
    
    km_per_lon_deg = degrees_to_km_conversion[0]
    km_per_lat_deg = degrees_to_km_conversion[1]
    mean_lon = degrees_to_km_conversion[2]
    mean_lat = degrees_to_km_conversion[3]

    num_of_groups = len(nodes_neighbouring_grouped)
    
    grouped_xy_coordinates = np.zeros((num_of_groups, len(data) * 2))

    # Initialize the grouped fields in the dataset
    for way in data:
        way['lon1_grouped'] = way['lon1']
        way['lat1_grouped'] = way['lat1']
        way['lon2_grouped'] = way['lon2']
        way['lat2_grouped'] = way['lat2']
    
    for i_group, group in enumerate(nodes_neighbouring_grouped):
        group_coords_lon = []
        group_coords_lat = []
        
        for node_id in group:
            way_id = node_id // 2
            endnode1 = (node_id % 2 == 0)
            
            if endnode1:
                group_coords_lon.append(data[way_id]['lon1'])
                group_coords_lat.append(data[way_id]['lat1'])
            else:
                group_coords_lon.append(data[way_id]['lon2'])
                group_coords_lat.append(data[way_id]['lat2'])
        
        mean_lon_group = np.mean(group_coords_lon)
        mean_lat_group = np.mean(group_coords_lat)
        
        for node_id in group:
            way_id = node_id // 2
            endnode1 = (node_id % 2 == 0)
            
            if endnode1:
                data[way_id]['lon1_grouped'] = mean_lon_group
                data[way_id]['lat1_grouped'] = mean_lat_group
            else:
                data[way_id]['lon2_grouped'] = mean_lon_group
                data[way_id]['lat2_grouped'] = mean_lat_group
                
            idx = group.index(node_id)
            grouped_xy_coordinates[i_group, 2 * idx] = mean_lon_group
            grouped_xy_coordinates[i_group, 2 * idx + 1] = mean_lat_group
    
    delta_lon1 = np.array([way['lon1_grouped'] for way in data]) - mean_lon
    delta_lon2 = np.array([way['lon2_grouped'] for way in data]) - mean_lon
    delta_lat1 = np.array([way['lat1_grouped'] for way in data]) - mean_lat
    delta_lat2 = np.array([way['lat2_grouped'] for way in data]) - mean_lat
    
    x1 = delta_lon1 * km_per_lon_deg
    x2 = delta_lon2 * km_per_lon_deg
    y1 = delta_lat1 * km_per_lat_deg
    y2 = delta_lat2 * km_per_lat_deg
    
    for i, way in enumerate(data):
        way['x1_grouped'] = x1[i]
        way['y1_grouped'] = y1[i]
        way['x2_grouped'] = x2[i]
        way['y2_grouped'] = y2[i]

        if np.isnan(way['x1_grouped']):
            way['x1_grouped'] = way['x1']
            way['y1_grouped'] = way['y1']
        if np.isnan(way['x2_grouped']):
            way['x2_grouped'] = way['x2']
            way['y2_grouped'] = way['y2']
    
    print('   ... finished! (%.3f seconds)' % (time.time() - start_time))
    
    return data, grouped_xy_coordinates


def my_add_final_coordinates(data):
    """
    DESCRIPTION
    This function selects the final coordinates: If one or both endnodes
    got grouped (because they were stacked and/or in a neighbourhood),
    those new grouped coordinates will be the final coordinates. If not,
    then the original coordinates will be taken as the final coordinates.

    INPUT
    data ... original dataset

    OUTPUT
    data ... updated dataset with new final coordinates fields
    """
    start_time = time.time()
    print('Start adding final coordinates...')

    for way in data:
        if 'ID_node1_grouped' in way:
            way['ID_node1_final'] = way['ID_node1_grouped']
            way['lon1_final'] = way['lon1_grouped']
            way['lat1_final'] = way['lat1_grouped']
            way['x1_final'] = way['x1_grouped']
            way['y1_final'] = way['y1_grouped']
        else:
            way['ID_node1_final'] = way['ID_node1']
            way['lon1_final'] = way['lon1']
            way['lat1_final'] = way['lat1']
            way['x1_final'] = way['x1']
            way['y1_final'] = way['y1']

        if 'ID_node2_grouped' in way:
            way['ID_node2_final'] = way['ID_node2_grouped']
            way['lon2_final'] = way['lon2_grouped']
            way['lat2_final'] = way['lat2_grouped']
            way['x2_final'] = way['x2_grouped']
            way['y2_final'] = way['y2_grouped']
        else:
            way['ID_node2_final'] = way['ID_node2']
            way['lon2_final'] = way['lon2']
            way['lat2_final'] = way['lat2']
            way['x2_final'] = way['x2']
            way['y2_final'] = way['y2']

    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    return data

def my_delete_singular_ways(data):
    """
    DESCRIPTION
    This function deletes all ways which have the same endpoints after
    grouping, hence got "shrinked" into a singularity.

    INPUT
    data ... original dataset

    OUTPUT
    data ... new dataset with singularity-ways deleted
    """
    start_time = time.time()
    print('Start deleting ways which have the same endpoints after grouping...')
                      
    way_IDs_singular = [i for i, way in enumerate(data) if way['ID_node1_final'] == way['ID_node2_final']]
    
    data_singular_ways = [data[i] for i in way_IDs_singular]
    
    data = [way for i, way in enumerate(data) if i not in way_IDs_singular]
    
    print(f'   ... {len(way_IDs_singular)} ways were deleted!')
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    
    return data, data_singular_ways

def my_calc_real_lengths(data_ways_selected, data_ways_all, data_nodes_all, settings):
    """
    DESCRIPTION
    This function calculates the real length of a line. It fetches all
    coordinates off all nodes of all UIDs, calculates the lenght between
    those segments and adds them all up to calcule the real length.
    
    INPUT
    data_ways_selected ... from which ways the real length should be
                           calcuated
    data_ways_all ... no ways have been doubled here, so fetch data here
    data_nodes_all ... get all coordinates of all nodes
    settings ... toogle on / off the whole function and specify visualisation
    
    OUTPUT
    data_ways_selected ... give each way its real line length
    lengths ... the struct used to calcualte the real line lengths
    """
    start_time = time.time()
    print('Start calculating real length of lines...')
    
    if settings.calculate_real_line_length:

        # Create variable with all coordinates of all nodes of all UID ways
        unique_UIDs = list(set(way['UID'] for way in data_ways_selected))

        # Create a list of all node ids
        list_all_node_IDs = [node['id'] for node in data_nodes_all]

        # Initalize the reverse string for realtime percentage status update
        reverse_string = ""

        # Calculate the number of UID-Ways
        numel_uids = len(unique_UIDs)

        lengths = []

        for i_uid, uid in enumerate(unique_UIDs):
            i_ways = next(index for index, way in enumerate(data_ways_all) if way['UID'] == uid)
            
            length_entry = {
                'UID': data_ways_all[i_ways]['UID'],
                'way_id': data_ways_all[i_ways]['id'],
                'nodes': []
            }

            for node_id in data_ways_all[i_ways]['nodes']:
                node_entry = {'id': node_id}
                position_current_node = list_all_node_IDs.index(node_id)
                node_entry['lon'] = data_nodes_all[position_current_node]['lon']
                node_entry['lat'] = data_nodes_all[position_current_node]['lat']
                length_entry['nodes'].append(node_entry)

            for j in range(1, len(length_entry['nodes'])):
                length_entry['nodes'][j-1]['next_lon'] = length_entry['nodes'][j]['lon']
                length_entry['nodes'][j-1]['next_lat'] = length_entry['nodes'][j]['lat']

            length_entry['length_org'] = data_ways_all[i_ways]['length']
            lengths.append(length_entry)

            #percent_done = 100 * (i_uid + 1) / numel_uids
            #string = f"   ... fetching coordinates of all nodes of way {i_uid + 1} of {numel_uids} ({percent_done:.2f} Percent)... \n"
            #print(reverse_string + string, end="")
            #reverse_string = '\b' * len(string)

        # Calculate beeline distance of each way
        print('   ... calculating length of each line segment...')
        earth_radius = 6371

        for length in lengths:
            lon_start_rad = length['nodes'][0]['lon'] * np.pi / 180
            lat_start_rad = length['nodes'][0]['lat'] * np.pi / 180
            lon_end_rad = length['nodes'][-1]['lon'] * np.pi / 180
            lat_end_rad = length['nodes'][-1]['lat'] * np.pi / 180

            delta_lon_rad = lon_end_rad - lon_start_rad
            delta_lat_rad = lat_end_rad - lat_start_rad

            x = delta_lon_rad * np.cos((lat_start_rad + lat_end_rad) / 2)
            y = delta_lat_rad
            length_of_line = np.sqrt(x**2 + y**2) * earth_radius

            length['length_beeline'] = length_of_line

        # Calculate distances of each segment
        for length in lengths:
            lons_start = [node['lon'] for node in length['nodes'][:-1]]
            lats_start = [node['lat'] for node in length['nodes'][:-1]]
            lons_end = [node['next_lon'] for node in length['nodes'][:-1]]
            lats_end = [node['next_lat'] for node in length['nodes'][:-1]]

            lons_start_rad = np.array(lons_start) * np.pi / 180
            lats_start_rad = np.array(lats_start) * np.pi / 180
            lons_end_rad = np.array(lons_end) * np.pi / 180
            lats_end_rad = np.array(lats_end) * np.pi / 180

            delta_lons_rad = lons_end_rad - lons_start_rad
            delta_lats_rad = lats_end_rad - lats_start_rad

            x = delta_lons_rad * np.cos((lats_start_rad + lats_end_rad) / 2)
            y = delta_lats_rad
            lengths_of_segments = np.sqrt(x**2 + y**2) * earth_radius

            for i, segment_length in enumerate(lengths_of_segments):
                length['nodes'][i]['segment_lengths'] = segment_length

            length['length_all_segments'] = np.sum(lengths_of_segments)
            length['length_diff_in_percent'] = length['length_all_segments'] / length['length_beeline'] * 100 - 100
            length['length_diff_absolut_in_km'] = length['length_all_segments'] - length['length_beeline']
            length['length_diff_between_org_and_beeline_percent'] = length['length_org'] / length['length_beeline'] * 100 - 100

        # Add that length to data_ways_selected too
        for way in data_ways_selected:
            current_UID = way['UID']
            length_entry = next(length for length in lengths if length['UID'] == current_UID)
            way['length_real'] = length_entry['length_all_segments']

        print(f'   ... finished! ({time.time() - start_time:.3f} seconds)')

        return data_ways_selected, lengths

    else:
        print('   ATTENTION: Real line length WONT be calculted! Beeline-length (Luftlinie) will be used.')
        return data_ways_selected, "Real line lengths have NOT been calculated!"


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
    
    data_tags = []
    
    for i, way in enumerate(data):
        if i > 0 and data_tags[-1]['UID'] == way['UID']:
            continue

        tags = {'UID': way['UID']}
        tags.update(way['tags'])
        data_tags.append(tags)
    
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    
    return data_tags

def my_add_LtgsID_clone_ways(data, export_excel_country_code):
    """
    DESCRIPTION
    This function creates the "LtgsID" for every way element.

    INPUT
    data ... input dataset
    export_excel_country_code ... the two-digit country code 

    OUTPUT
    data_new ... new dataset with cloned ways and field "LtgsID"
    """
    start_time = time.time()
    print('Start adding "LtgsID" and cloning ways...')
    
    num_of_ways = len(data)
    num_of_doubled_ways = 0
    num_of_tripled_ways = 0
    num_of_quadrupled_ways = 0
    data_new = []
   
    LtgsID_Prefix = f'LTG{export_excel_country_code}'
    LtgsID = [f'{LtgsID_Prefix}{i:04d}' for i in range(1, num_of_ways + 1)]
                
    for i in range(num_of_ways):
        data[i]['LtgsID'] = LtgsID[i]
   
    i_ways_new = 0
    for way in data:
        if way['systems'] == 2:
            cloned_way_b = way.copy()
            LtgsID_current = way['LtgsID']
            way['LtgsID'] = f'{LtgsID_current}a'
            cloned_way_b['LtgsID'] = f'{LtgsID_current}b'
            data_new.extend([way, cloned_way_b])
            num_of_doubled_ways += 1
            i_ways_new += 2
        elif way['systems'] == 3:
            cloned_way_b = way.copy()
            cloned_way_c = way.copy()
            LtgsID_current = way['LtgsID']
            way['LtgsID'] = f'{LtgsID_current}a'
            cloned_way_b['LtgsID'] = f'{LtgsID_current}b'
            cloned_way_c['LtgsID'] = f'{LtgsID_current}c'
            data_new.extend([way, cloned_way_b, cloned_way_c])
            num_of_tripled_ways += 2
            i_ways_new += 3
        elif way['systems'] == 4:
            cloned_way_b = way.copy()
            cloned_way_c = way.copy()
            cloned_way_d = way.copy()
            LtgsID_current = way['LtgsID']
            way['LtgsID'] = f'{LtgsID_current}a'
            cloned_way_b['LtgsID'] = f'{LtgsID_current}b'
            cloned_way_c['LtgsID'] = f'{LtgsID_current}c'
            cloned_way_d['LtgsID'] = f'{LtgsID_current}d'
            data_new.extend([way, cloned_way_b, cloned_way_c, cloned_way_d])
            num_of_quadrupled_ways += 3
            i_ways_new += 4
        else:
            data_new.append(way)
            i_ways_new += 1

    print(f'   ... {num_of_doubled_ways} ways have been doubled, {num_of_tripled_ways // 2} tripled, {num_of_quadrupled_ways // 3} quadrupled.')
    print(f'   ... finished! ({time.time() - start_time:.3f} seconds) \n')
    
    return data_new

import pandas as pd
import numpy as np
from datetime import datetime
import time

def my_export_excel(data, export_excel_country_code, data_tags, way_length_multiplier):
    """
    DESCRIPTION
    This function exports the data to two excel files. Every unique endnode
    will recive a NUID (unique node ID), this too will be added to the
    added to the dataset. Columns will be created so that ATLANTIS can
    read the excel file. In the annotation ("Bemerkung") column additinal
    information will be written if necessary.
    
    INPUT
    data ... the dataset to export
    export_excel_country_code ... the countrycode to name LtgsID and NUID
    data_tags ... all values off all fields of all tags of all way elements
    
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

    # Go through every NUID and assign it to data_ways_selected
    # where the node ID and the voltage level matches
    for i_nuid in range(len(nodes_unique)):
        # Get the original node ID of current NUID
        node_org_ID = int(float(nodes_conversion[i_nuid, 1]))
        # Get the voltage level of current NUID
        node_org_voltage = int(float(nodes_conversion[i_nuid, 2]))

        # Create a boolean index which node1 has exactly that org_ID
        b_node1_ID_match = node1_data[:, 0] == node_org_ID
        b_node2_ID_match = node2_data[:, 0] == node_org_ID

        # Create a boolean index which voltage matches current NUID voltage
        b_node1_voltage_match = node1_data[:, 1] == node_org_voltage
        b_node2_voltage_match = node2_data[:, 1] == node_org_voltage

        # Create a boolean index when both conditions are met
        b_node1_id_and_voltage_ok = b_node1_ID_match & b_node1_voltage_match
        b_node2_id_and_voltage_ok = b_node2_ID_match & b_node2_voltage_match

        # Assign every node which satisfies both conditions current NUID
        for way in data:
            if way['ID_node1_final'] == node_org_ID and way['voltage'] == node_org_voltage:
                way['node1_nuid'] = nuid[i_nuid]
            if way['ID_node2_final'] == node_org_ID and way['voltage'] == node_org_voltage:
                way['node2_nuid'] = nuid[i_nuid]

    # Create strings for the Annotation "Bemerkung" column   
    str_annotation = ["" for _ in range(num_of_ways)]

    # go through all ways
    for i_ways in range(num_of_ways):
        # Create string if current way has multiple voltage levels
        if data[i_ways]['vlevels'] != 1:
            str_annotation[i_ways] += ", multiple vlevels"

        # Create string if current way is doubled/tripled/quadrupled
        if data[i_ways]['systems'] == 2:
            str_annotation[i_ways] += ", 6 cables - 2 systems"
        elif data[i_ways]['systems'] == 3:
            str_annotation[i_ways] += ", 9 cables - 3 systems"
        elif data[i_ways]['systems'] == 4:
            str_annotation[i_ways] += ", 12 cables - 4 systems"

        # Create string if current way is DC candidate
        if data[i_ways]['dc_candidate']:
            str_annotation[i_ways] += ", potentially DC"

        # Add a blank space if no annotation was made
        if not str_annotation[i_ways]:
            str_annotation[i_ways] = " "

    # Create column 'Note'
    UID = [str(way['UID']) for way in data]
    Note = ["UID: " + uid + note for uid, note in zip(UID, str_annotation)]

    # Get the "fromNode" and "toNode" NUIDs
    fromNode = [way['node1_nuid'] for way in data]
    toNode = [way['node2_nuid'] for way in data]

    # Create column 'SpgsebeneWert'
    Voltage = [way['voltage'] / 1000 for way in data]

    # Create column 'LtgLaenge', take real length if it exists, otherwise beeline length
    if 'length_real' in data[0]:
        Length = [way['length_real'] for way in data]
        print('INFO: Real line length got used (segmentwise calculation)!')
    else:
        Length = [way['length'] for way in data]
        print('INFO: simplified line length got used (beeline - Luftlinie)!')

    # Compensate for slack
    Length = np.round(np.array(Length) * way_length_multiplier, 2)

    print(f'INFO: Length of each line got multiplied by {way_length_multiplier:.2f} for slack compensation!')

    # Create column 'LtgsID'
    LineID = [way['LtgsID'] for way in data]

    # Create column 'Land'   
    Country = [export_excel_country_code] * num_of_ways

    # Create all 0-entry columns for "Stamm_Leitungen"
    R = XL = XC = Itherm = Capacity = PhiPsMax = [0] * num_of_ways

    # Export "Stamm_Leitungen" to Excel   
    str_timestamp = time.strftime('%Y-%m-%d_%H-%M-%S')
    str_cc = f'{export_excel_country_code}_'

    table_leitungen = pd.DataFrame({
        'LineID': LineID,
        'Country': Country,
        'fromNode': fromNode,
        'toNode': toNode,
        'Voltage': Voltage,
        'R': R,
        'XL': XL,
        'XC': XC,
        'Itherm': Itherm,
        'Length': Length,
        'Capacity': Capacity,
        'Note': Note,
        'PhiPsMax': PhiPsMax
    })

    folder_path = "C:/Users/gezz/Documents/Uni/Master/Masterarbeit/GridTool-main/Aktuelle_Version/Excel-Files/"
    filename_lines = folder_path + f'Python_tbl_Lines_{str_cc}{str_timestamp}.xlsx'
    
    with pd.ExcelWriter(filename_lines, engine='xlsxwriter') as writer:
        table_leitungen.to_excel(writer, sheet_name='Sheet1', index=False)
        pd.DataFrame(data_tags).to_excel(writer, sheet_name='Sheet2', index=False)

    print('INFO: In "tbl_Lines.xlsx" in  "Sheet 2" all tags from all UIDs are listed! Have a look for data inspection!')

    # Get all the other variables needed for export "Nodes.xlsx" 
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


def my_plot_ways_original(data, data_busbars, voltage_levels_selected, settings, data_singular_ways):
    """
    DESCRIPTION
    This function plots the original dataset as it was. Two plots will
    be generated if the flag in "bool" was set: A plot with a lon/lat
    coordinate system and a plot with an inaccurate, but more intuitive
    x/y plot in km. Since Matlab is a bit tricky with legends and color
    coding of same plots, a workaround with pseudo-points is necessary.
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
        colormap = np.array([[ 51,160, 44],  [ 31,120,180], [177, 89, 40], [106, 61,154],
                            [255,127,  0], [178,223,138], [227, 26, 28], [255,255,153], 
                            [166,206,227], [202,178,214], [251,154,153], [253,191,111]]) / 255.0

        # Create a warning if colors of voltage levels do repeat
        if len(voltage_levels_selected) > 12:
            print('   ATTENTION!  More than 12 voltage levels are selected.')
            print('               Colors of voltage lines do repeat now!')
            print('               It is recommended to select max. 12 voltage levels.')

        # Create figure for deg Plot
        plt.figure()
        plt.title('Original ways, only selected voltages, lon/lat coordinates')
        plt.xlabel('Longitude [°]')
        plt.ylabel('Latitude [°]')
        plt.grid(True)
    
        # Calculate midpoint to place the pseudo-points
        try:
            lat_mean = np.mean([way['lat1'] for way in data if way is not None] + [way['lat2'] for way in data if way is not None])
            lon_mean = np.mean([way['lon1'] for way in data if way is not None] + [way['lon2'] for way in data if way is not None])
        except Exception as e:
            print(f"Error calculating lat_mean and lon_mean: {e}")
            return

        for i_vlevel in range(len(voltage_levels_selected)-1, -1, -1):

            i_colormap = i_vlevel % 12

            current_color = colormap[i_colormap]

            plt.plot(lon_mean, lat_mean, 'o-' , color=current_color)

        labels = [f'{vlevel/1000} kV' for vlevel in reversed(voltage_levels_selected)]

        plt.legend(labels, loc='northwest', frameon=False)

        plt.plot(lon_mean, lat_mean, 'o-' , color='white')

        busbars_lon = np.array([busbar['lon1'] for busbar in data_busbars] + [busbar['lon2'] for busbar in data_busbars])
        busbars_lat = np.array([busbar['lat1'] for busbar in data_busbars] + [busbar['lat2'] for busbar in data_busbars])

        plt.plot(busbars_lon, busbars_lat, 'cx-', linewidth=1)

        singular_lon = np.array([way['lon1'] for way in data_singular_ways] + [way['lon2'] for way in data_singular_ways])
        singular_lat = np.array([way['lat1'] for way in data_singular_ways] + [way['lat2'] for way in data_singular_ways])

        plt.plot(singular_lon, singular_lat, 'kx-', linewidth=1)

        for i_vlevel in range(len(voltage_levels_selected)-1, -1, -1):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]
            current_voltage = voltage_levels_selected[i_vlevel]
            b_current_voltage = [way['voltage'] == current_voltage for way in data]
            current_ways = [data[i] for i in range(len(data)) if b_current_voltage[i]]

            lon = np.array([way['lon1'] for way in current_ways] + [way['lon2'] for way in current_ways])
            lat = np.array([way['lat1'] for way in current_ways] + [way['lat2'] for way in current_ways])

            plt.plot(lon, lat, '-o', color=current_color)

        plt.show(block=False)

        # Create figure for X/Y km Plot
        plt.figure()
        plt.title('Original ways, only selected voltages, x/y coordinates')
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        plt.grid(True)
        
        for i_vlevel in range(len(voltage_levels_selected)-1, -1, -1):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]
            plt.plot(0, 0, 'o-' , color=current_color)

        labels = [f'{vlevel/1000} kV' for vlevel in reversed(voltage_levels_selected)]

        plt.legend(labels, loc='northwest', frameon=False)
        plt.plot(0, 0, 'o-' , color='white')
                    
        busbars_x = np.array([busbar['x1'] for busbar in data_busbars] + [busbar['x2'] for busbar in data_busbars])
        busbars_y = np.array([busbar['y1'] for busbar in data_busbars] + [busbar['y2'] for busbar in data_busbars])

        plt.plot(busbars_x, busbars_y, 'cx-', linewidth=1)
        
        singular_x = np.array([way['x1'] for way in data_singular_ways] + [way['x2'] for way in data_singular_ways])
        singular_y = np.array([way['y1'] for way in data_singular_ways] + [way['y2'] for way in data_singular_ways])

        plt.plot(singular_x, singular_y, 'kx-', linewidth=1)
        
        for i_vlevel in range(len(voltage_levels_selected)-1, -1, -1):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]
            current_voltage = voltage_levels_selected[i_vlevel]
            b_current_voltage = [way['voltage'] == current_voltage for way in data]
            current_ways = [data[i] for i in range(len(data)) if b_current_voltage[i]]

            x = np.array([way['x1'] for way in current_ways] + [way['x2'] for way in current_ways])
            y = np.array([way['y1'] for way in current_ways] + [way['y2'] for way in current_ways])

            plt.plot(x, y, '-o', color=current_color)
        
        plt.show(block=False)

        print(f'   ... finished! ({time.time() - start_time:.3f} seconds)')


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
        
        plt.figure()
        plt.title('Original and final ways with grouping-circles')
        plt.xlabel('x - distance from midpoint [km]')
        plt.ylabel('y - distance from midpoint [km]')
        plt.grid(True)
        
        # Filter out None values from data
        data = [way for way in data if way is not None]
        
        if not data:
            print('No valid data to plot.')
            return
        
        try:
            x = np.concatenate(([way['x1'] for way in data], [way['x2'] for way in data]))
            y = np.concatenate(([way['y1'] for way in data], [way['y2'] for way in data]))
        except KeyError as e:
            print(f'Missing key in data: {e}')
            return

        plt.plot(x, y, 'o--k', color=[0.6, 0.6, 0.6])

        busbars_lon = np.array([busbar['lon1'] for busbar in data_busbars] + [busbar['lon2'] for busbar in data_busbars])
        busbars_lat = np.array([busbar['lat1'] for busbar in data_busbars] + [busbar['lat2'] for busbar in data_busbars])

        plt.plot(busbars_lon, busbars_lat, 'o--', color=[0.6, 0.6, 0.6])

        origin_circles = np.reshape([coord for group in grouped_xy_coordinates for coord in group if coord is not None], (-1, 2))
        radii = neighbourhood_threshold * np.ones(origin_circles.shape[0])
        for circle in origin_circles:
            circle_plot = plt.Circle(circle, neighbourhood_threshold, color='b', fill=False, linestyle=':')
            plt.gca().add_patch(circle_plot)

        try:
            x_final = np.concatenate(([way['x1_final'] for way in data], [way['x2_final'] for way in data]))
            y_final = np.concatenate(([way['y1_final'] for way in data], [way['y2_final'] for way in data]))
        except KeyError as e:
            print(f'Missing key in data: {e}')
            return

        plt.plot(x_final, y_final, 'k-o')

        x_grouped = np.concatenate(([way['x1_grouped'] for way in data], [way['x2_grouped'] for way in data]))
        y_grouped = np.concatenate(([way['y1_grouped'] for way in data], [way['y2_grouped'] for way in data]))

        plt.plot(x_grouped, y_grouped, '.m', markersize=15)

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

        colormap = np.array([
            [51, 160, 44], [31, 120, 180], [177, 89, 40], [106, 61, 154],
            [255, 127, 0], [178, 223, 138], [227, 26, 28], [255, 255, 153], 
            [166, 206, 227], [202, 178, 214], [251, 154, 153], [253, 191, 111]
        ]) / 255.0

        if len(voltage_levels_selected) > 12:
            print('ATTENTION! More than 12 voltage levels are selected. Colors of voltage lines will repeat. It is recommended to select max. 12 voltage levels.')

        fig1, ax1 = plt.subplots()
        ax1.set_title('Final ways as exported, lon/lat coordinates')
        ax1.set_xlabel('Longitude [°]')
        ax1.set_ylabel('Latitude [°]')
        ax1.grid(True)

        lat_mean = np.mean([way['lat1_final'] for way in data if way['lat1_final'] is not None] + 
                           [way['lat2_final'] for way in data if way['lat2_final'] is not None])
        lon_mean = np.mean([way['lon1_final'] for way in data if way['lon1_final'] is not None] + 
                           [way['lon2_final'] for way in data if way['lon2_final'] is not None])

        for i_vlevel in reversed(range(len(voltage_levels_selected))):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]
            current_voltage = voltage_levels_selected[i_vlevel]

            b_current_voltage = [way for way in data if way['voltage'] == current_voltage]

            lon = [way['lon1_final'] for way in b_current_voltage] + [way['lon2_final'] for way in b_current_voltage]
            lat = [way['lat1_final'] for way in b_current_voltage] + [way['lat2_final'] for way in b_current_voltage]

            ax1.plot(lon, lat, '-o', color=current_color)

        labels = [f"{v/1000} kV" for v in reversed(voltage_levels_selected)]
        ax1.legend(labels, loc='northwest', frameon=False)

        fig2, ax2 = plt.subplots()
        ax2.set_title('Final ways as exported, x/y coordinates')
        ax2.set_xlabel('x - distance from midpoint [km]')
        ax2.set_ylabel('y - distance from midpoint [km]')
        ax2.grid(True)

        for i_vlevel in reversed(range(len(voltage_levels_selected))):
            i_colormap = i_vlevel % 12
            current_color = colormap[i_colormap]
            current_voltage = voltage_levels_selected[i_vlevel]

            b_current_voltage = [way for way in data if way['voltage'] == current_voltage]

            x = [way['x1_final'] for way in b_current_voltage] + [way['x2_final'] for way in b_current_voltage]
            y = [way['y1_final'] for way in b_current_voltage] + [way['y2_final'] for way in b_current_voltage]

            ax2.plot(x, y, '-o', color=current_color)

        labels = [f"{v/1000} kV" for v in reversed(voltage_levels_selected)]
        ax2.legend(labels, loc='northwest', frameon=False)

        plt.show()
        print(f'   ... finished! ({time.time() - start_time:.3f} seconds)')

class Settings:
    def __init__(self):
        self.calculate_real_line_length = True
        self.plot_ways_original = False
        self.plot_ways_grouping = False
        self.plot_ways_final = False
        self.histogram_length_busbars = False
        self.histogram_stacked_endnodes = False
        self.histogram_neighbouring_endnodes = False
        self.histogram_distances_between_endpoints = False
        self.plot_stacked_endnodes = False
        self.plot_neighbouring_endnodes = False
        self.beeline_visu_treshold_diff_percent = 1.0
        self.beeline_visu_treshold_diff_absolut = 1.0

settings = Settings()

def export_data(data_list, output_file):
    with open(output_file, 'w') as file:
        for line in data_list:
            nodes = line['nodes']
            
            nodes_str = "["
            for node in nodes:
                nodes_str += str(node)+ ' '
            nodes_str += ']'
            
            node_id = str(line['id'])
            tags = str(line['tags'])
            node_type = str(line['type'])
            UID = str(line['UID'])
            ID_node1 = str(line['ID_node1'])
            ID_node2 = str(line['ID_node2'])
            lon1 = str(line['lon1'])
            lat1 = str(line['lat1'])
            lon2 = str(line['lon2'])
            lat2 = str(line['lat2'])
            x1 = str(line['x1'])
            y1 = str(line['y1'])
            x2 = str(line['x2'])
            y2 = str(line['y2'])
            length = str(line['length'])
            voltage = str(int(line['voltage']))
            vlevels = str(line['vlevels'])
            busbar = str(line['busbar'])
            dc = str(line['dc_candidate'])


            if 'dc_candidate' in line:
                file.write(node_type + ', ' + node_id + ', ' + nodes_str + ', ' + UID + ', ' + ID_node1 + ', ' + ID_node2 + ', ' + lon1 + ', '
                           + lat1 + ', ' + lon2 + ', ' + lat2 + ', ' + x1 + ', ' + y1 + ', ' + x2 + ', ' + y2 + ', ' + length + ', ' + voltage + ', '
                           + vlevels + ', ' + busbar + ', ' + dc + ', ' +'\n')
            elif 'busbar' in line and 'dc_candidate' not in line:
                file.write(node_type + ', ' + node_id + ', ' + nodes_str + ', ' + UID + ', ' + ID_node1 + ', ' + ID_node2 + ', ' + lon1 + ', '
                           + lat1 + ', ' + lon2 + ', ' + lat2 + ', ' + x1 + ', ' + y1 + ', ' + x2 + ', ' + y2 + ', ' + length + ', ' + voltage + ', '
                           + vlevels + ', ' + busbar + '\n')
            elif 'voltage' in line and 'busbar' not in line:
                file.write(node_type + ', ' + node_id + ', ' + nodes_str + ', ' + UID + ', ' + ID_node1 + ', ' + ID_node2 + ', ' + lon1 + ', '
                           + lat1 + ', ' + lon2 + ', ' + lat2 + ', ' + x1 + ', ' + y1 + ', ' + x2 + ', ' + y2 + ', ' + length + ', ' + voltage + ', '
                           + vlevels + '\n')
                
            elif 'ID_node1' in line:
                file.write(node_type + ', ' + node_id + ', ' + nodes_str + ', ' + UID + ', ' + ID_node1 + ', ' + ID_node2 + ', ' + lon1 + ', '
                           + lat1 + ', ' + lon2 + ', ' + lat2 + ', ' + x1 + ', ' + y1 + ', ' + x2 + ', ' + y2 + ', ' + length + '\n')
            else:
                file.write(node_type + ', ' + node_id + ', ' + nodes_str + ', ' + UID + '\n')
            
def main_program():
    overallruntime_start = time.time()
    
    # Print welcome message and a few settings
    if settings.calculate_real_line_length:
        string_real_length = 'Real line length WILL be calculated'
    else:
        string_real_length = 'Real line length NOT be calculated'
    
    print(f'''WELCOME to GridTool!
(C) created by Lukas Frauenlob and Robert Gaugl, IEE, TU Graz
Updated by Jürgen Reiter, TU Graz

--- Info ---
   ... to restart data import, please delete variable "data_raw". 
   ... to restart voltage level selection, delete "voltage_levels_selected". 
   ... please check if visualisations are toggled on/off for either 
       performance improvements or additional information!

--- Settings --- 
   ... Country code for Excel output: "{export_excel_country_code}" 
   ... Neighbouring (=grouping circle) threshold: {neighbourhood_threshold:5.2f} km 
   ... {string_real_length} 
   ... Line length slack compensation factor: {way_length_multiplier:3.2f}
''')
    
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
    data_ways_all, degrees_to_km_conversion = my_add_coordinates(data_ways_all, data_nodes_all)
    #export_data(data_ways_all, "data_ways_all_coord_python.txt")
    
    # Select voltage levels
    print('\n--- Select voltage levels (Step 2/6) ---')

    # Count the number of lines with a specific voltage level, display and add it 
    data_ways_all, voltage_levels_sorted = my_count_voltage_levels(data_ways_all)
    #export_data(data_ways_all, "data_ways_all_voltage_python.txt")
    
    # Open a dialog to ask the user to select voltage levels 
    if 'voltage_levels_selected' not in locals():
        voltage_levels_selected = my_ask_voltage_levels(voltage_levels_sorted)

    # Save all ways which match selected voltage levels
    data_ways_selected = my_select_ways(data_ways_all, voltage_levels_selected)
    #export_data(data_ways_selected, "data_ways_all_voltage_selected_python.txt")
    
    # Analyse data
    print('\n--- Analyse data (Step 3/6) ---')

    # Find all ways with type busbars, extract them and delete them
    data_ways_selected, data_busbars = my_delete_busbars(data_ways_selected, settings, busbar_max_length)
    #export_data(data_ways_selected, "data_ways_selected_withput_busbars_python.txt")
    #export_data(data_busbars, "data_busbars_python.txt")

##    for line in data_ways_selected:
##        print(str(line['length']) + '\n')

    # Detect all possible DC lines
    data_ways_selected, dc_candidates = my_count_possible_dc(data_ways_selected)
    export_data(data_ways_selected, "data_ways_selected_without_dc_python.txt")

    
##    for dc in dc_candidates:
##        print(str(dc['UID']) + ', ' + str(dc['voltage_level']) + ', ' + str(dc['reason']))

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

    # Add LtgsID and duplicate ways if necessary
    data_ways_selected = my_add_LtgsID_clone_ways(data_ways_selected, export_excel_country_code)
                                  
    # Export data to excel files, add NUID
    data_ways_selected = my_export_excel(data_ways_selected, export_excel_country_code, data_ways_selected_tags, way_length_multiplier)

########################################################################################################################
    # Visualisations
##    print('\n--- Visualisations (Step 6/6) ---')

##    # Plot original ways
##    my_plot_ways_original(data_ways_selected, data_busbars, voltage_levels_selected, settings, data_singular_ways)
##
##    # Plot ways while grouping endnodes
##    my_plot_ways_grouping(data_ways_selected, data_busbars, grouped_xy_coordinates, neighbourhood_threshold, settings)
##
##    # Plot final ways
##    my_plot_ways_final(data_ways_selected, voltage_levels_selected, settings)
########################################################################################################################
    
    print(f'\n\nOverall runtime of program: {time.time() - overallruntime_start:.3f} seconds. \nCONVERSION COMPLETED \n \n')

if __name__ == "__main__":
    main_program()
