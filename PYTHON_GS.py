#READ DATA FROM RADIOSONDE->INPUT GS COORDINATES->COMPUTE AZ/EL->send data to arduino
import sondehub
import pyproj 
import numpy as np
from math import atan2, degrees
import json
import time

#Pyserial
import serial

# Define the serial port and baud rate
#ser = serial.Serial('COM5', 115200)  # Change 'COM5' to match your Arduino's port

#UI dashboard
#this runs on port 8050
import dash
from dash.dependencies import Input, Output
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go


#to do
#Remember previous position
#GNSS yaw calibration to find 0
#IMU tilt to find 0 angle
#different tracking intervals for ascent vs descent, with descent being faster, till be shorter time between updates
#pair up with a sonde autorx for decoding for low latency

data=[]

app = dash.Dash(__name__)

rx_lla_coords=[ 1.2735524435709134, 103.81766488105683,106] #lat,lon,altitude
flag=False
initial_zoom = 5  # Initial zoom level


# Layout of the app
app.layout = html.Div(children=[
    dcc.Graph(id='live-map'),
    html.P(id='live-text'),  # Paragraph text
    dcc.Interval(
        id='interval-component',
        interval=1000,  # Update every 1 second
        n_intervals=0
    ),
    html.Div(id='zoom', style={'display': 'none'}, children=initial_zoom)  # Hidden div to store zoom level
])


def on_message(data_in):
    global data
    message_decoded = data_in.decode('utf-8')
    message= json.loads(message_decoded)
    
    data_out=[message['lat'],message['lon'],message['alt']]
    data=data_out

    
    return data    

def gps_to_ecef_pyproj(coordinates):
    lat=coordinates[0]
    
    lon=coordinates[1]
    alt=coordinates[2]
    print(lon,lat,alt)
    ecef = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
    lla = pyproj.Proj(proj='latlong', ellps='WGS84', datum='WGS84')
    x, y, z = pyproj.transform(lla, ecef, lon, lat,alt, radians=False)
    
    ecef_coords=[x,y,z]

    return ecef_coords



def compute_az_el(target,station):
    geod = pyproj.Geod(ellps='WGS84')
   
    # Compute the azimuth, back azimuth, and distance between the target and the station
    azimuth, _, distance = geod.inv(station[1], station[0], target[1], target[0])
    azimuth=azimuth%360  #So as to not get negative angles
    
    # Compute the altitude difference
    altitude_difference = target[2] - station[2]

    # Compute the elevation angle using the distance and the height difference
    elevation_deg = degrees(atan2(altitude_difference,distance))#atan(y/x)!!

    return azimuth,elevation_deg

def compute(data):
    target_lla_coords=data
    target_ecef_coords=gps_to_ecef_pyproj(target_lla_coords)
    rx_ecef_coords=gps_to_ecef_pyproj(rx_lla_coords)
   
    Azimuth,Elevation=compute_az_el(target_lla_coords,rx_lla_coords)

    return Azimuth,Elevation

def arduino_angle(actuator_angles): #sends the az and el angles as floating point arrays
    # Convert list of floats to bytes
    data_bytes = ','.join(map(str, actuator_angles)).encode('utf-8')
    
    # Write the data to the serial port
    ser.write(data_bytes)
    ser.flush()  # Ensure all the data is sent
    
    # Delay to allow time for Arduino to process data
    time.sleep(1)

def read_from_arduino():
    # Read data from the serial port
    while ser.in_waiting == 0:
        pass    #do nothing if no serial output from arduino

    if ser.in_waiting>0:
        # Read the data from the serial port
        data_arduino = ser.readline()

        #code in arduino
        '''
        Serial.print(az_position);
        Serial.println(',');
        Serial.println(el_position);
        '''
        print("Data from Arduino:", data_arduino) #this should read out  b'Rotator positions: AZ: 1158, EL: 365\r\n'



#html stuff
# Callback to update the map
@app.callback(Output('live-map', 'figure'),
            Output('live-text', 'children'),
            [Input('interval-component', 'n_intervals')])

def update_map(n):
    
    fig = go.Figure(go.Scattermapbox(
    mode = "markers+lines",
    lon = [data[1],rx_lla_coords[1]], #set of longitudes
    lat = [data[0],rx_lla_coords[0]],  #set of latitudes
    marker = {'size': 10}))

    fig.update_layout(
    margin ={'l':0,'t':0,'b':0,'r':0},
    mapbox = {
        'center': {'lon': 103.8198, 'lat': 1.3521}, #1.3521° N, 103.8198°E
        'style': "open-street-map",
        'zoom': 10})
        
    Azimuth,Elevation=compute(data) #these are local variables
    text =f"AZ and EL: AZ={Azimuth}, Elevation:{Elevation}, target coords:{data[0],data[1],data[2]}"

    return fig,text


    

    
    
    
    
    

#test code, just sends az el every 10 seconds


if __name__ == '__main__':

    #this part ensures that the stream has all data points needed befor continuing

    
    

    ##################arduino rotator portion########################
    
    #test code w/o live data 
    #Azimuth=[0.0,250.0,261.0,272.0,283.0,294.0,285.0,276.0,267.0,258.0,240.0,233.0,223.0,210.0,0.0]
    #Elevation=[0.0,10.0,21.0,32.0,43.0,54.0,65.0,76.0,87.0,78.0,59.0,30.0,21.0,15.0,0.0]
    #to_arduino=[Azimuth[i],Elevation[i]] #floating point array to be sent to arduino using serial
    while(True):
        while flag==False:
            #compute ECEF coordinates
            sondehub.Stream(on_message=on_message, sondes=["3102054"],asJson=True)
            #print(data)

            if len(data) < 3:
                print("Number of indexes in the list is not above 3. Exiting program.")
            
            else:
                flag=True
                print("Continuing with the program...")

        '''
        Azimuth,Elevation=compute()

        #add a memoery feature to remember the last angle.

        to_arduino=[Azimuth,Elevation] #floating point array to be sent to arduino using serial
        arduino_angle(to_arduino) #send through serial, will loop here if no messages of rotator sent from arduino
        print(to_arduino)
        print('Exceucting turn')
        time.sleep(1) #this time is to let the arduino process the data           
        read_from_arduino()
        #set up coms with dashboard
        '''
        #update dashboard
        app.run_server(debug=True) #app.callback() means this is ran again.
    

    
    




'''
message={"software_name": "radiosonde_auto_rx", 
"software_version": "1.7.2", 
"uploader_callsign": "DVZ BASE", 
"uploader_position": "1.5462,103.7197", 
"uploader_antenna": "1/4 wave monopole", 
"time_received": "2024-05-23T11:44:22.094596Z", 
"datetime": "2024-05-23T11:44:20.000000Z", 
"manufacturer": "Meisei", 
"type": "iMS-100", 
"serial": "3102061", 
"frame": 10766, 
"lat": 1.19827, 
"lon": 103.74791, 
"alt": 16873.4, 
"temp": -84.3, 
"humidity": 30.2, 
"vel_v": 2.8809, 
"vel_h": 14.30159, 
"heading": 242.7, 
"frequency": 401.889, 
"ref_position": "MSL", 
"ref_datetime": "UTC", 
"snr": 17.1, 
"tx_frequency": 401.9, 
"user-agent": "Amazon CloudFront", 
"position": "1.19827,103.74791", 
"upload_time_delta": -1.371, 
"uploader_alt": 0.0}
'''