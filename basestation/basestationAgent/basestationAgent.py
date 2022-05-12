#!/usr/bin/env python3
import socket
import pickle
import json
import geojson as gj
import sys

from flypawClasses import iperfInfo, sendVideoInfo, collectVideoInfo, flightInfo, missionInfo, resourceInfo, VehicleCommands
from cloud_resources import CloudResources

sys.path.append('/root/Profiles/vehicle_control/aerpawlib/')
#from aerpawlib.vehicle import Drone
#from aerpawlib.vehicle import Vehicle
#import dronekit

#import aerpawlib
from datetime import datetime

def getMissionLibraries(mission):
    missionLibraries = []
    if 'missionType' in mission:
        missiontype = mission['missionType']
        if missiontype == "bandwidth":
            missionLibraries.append("iperf3")
    return missionLibraries

def getMissionResourceCommands(mission):
    missionResourceCommands = []
    if 'missionType' in mission:
        missiontype = mission['missionType']
        if missiontype == "bandwidth":
            missionResourceCommands.append("iperf3 --server -J -D --logfile iperf3.txt")
    return missionResourceCommands

def getPlanFromPlanfile(filepath):
    f = open(filepath)
    pathdata = json.load(f)
    f.close()
    return pathdata

def processPlan(plan):
    processedPlan = {}
    default_waypoints = []
    if not 'mission' in plan:
        print("No mission in planfile")
        return None
    if not 'plannedHomePosition' in plan['mission']:
        print("No planned home position")
        return None
    php = plan['mission']['plannedHomePosition']

    thisWaypoint = [php[1],php[0],0]
    default_waypoints.append(thisWaypoint)
    lastWaypoint = thisWaypoint
    if not 'items' in plan['mission']:
        print("No items")
        return None
    theseItems = plan['mission']['items']
    for thisItem in theseItems:
        if 'autocontinue' in thisItem:
            if thisItem['autocontinue'] == True:
                print ("ignore autocontinue")
                thisWaypoint = [php[1],php[0],lastWaypoint[2]]
                processedPlan['default_waypoints'] = default_waypoints
                thisWaypoint = [php[1],php[0],0]
                default_waypoints.append(thisWaypoint)
        if 'params' in thisItem:
            if not len(thisItem['params']) == 7:
                print("incorrect number of params")
            else:
                thisWaypoint = [thisItem['params'][5], thisItem['params'][4], thisItem['params'][6]]
                if thisWaypoint[0] == 0:
                    thisWaypoint[0] = lastWaypoint[0]
                if thisWaypoint[1] == 0:
                    thisWaypoint[1] = lastWaypoint[1]
                default_waypoints.append(thisWaypoint)
                lastWaypoint = thisWaypoint

    print (default_waypoints)
    processedPlan['default_waypoints'] = default_waypoints
    return processedPlan

class FlyPawBasestationAgent(object):
    def __init__(self, ipaddr="172.16.0.1", port=20001, chunkSize=1024) :
        self.ipaddr = ipaddr
        self.port = port
        self.chunkSize = chunkSize
        self.iperf3Agent = iperfInfo()
        self.videoTransferAgent = sendVideoInfo()
        self.videoCollectionAgent = collectVideoInfo()
        self.flightInfo = flightInfo()
        self.missions = []
        self.currentRequests = []
        self.iperfHistory = []
        self.resourceList = []
        #self.drone = Drone() #our digital twin
        self.droneSim = droneSim()
        self.vehicleCommands = VehicleCommands()
        self.vehicleCommands.setIperfCommand(self.iperf3Agent)
        self.vehicleCommands.setCollectVideoCommand(self.videoCollectionAgent)
        self.vehicleCommands.setSendVideoCommand(self.videoTransferAgent)
        self.acs = "https://casa-denton3.noaa.unt.edu:8091/casaAlert/flightPath"
        self.usrname = "admin"
        self.password = "shabiz"
        self.updateURL = "https://casa-denton3.noaa.unt.edu:8091/casaAlert/flightUpdate"
        #for mission data, we should probably be checking elsewhere... for now we'll just define a mission here:
        mission = missionInfo()
        mission.name = "AERPAW"
        mission.missionType = "bandwidth" #"videography"
        mission.missionLeader = "drone" #or basestation or cloud
        mission.priority = 1
        mission.planfile = "./plans/mission.plan"
        mission.default_waypoints = []
        plan = getPlanFromPlanfile(mission.planfile)
        processedPlan = processPlan(plan)
        mission.default_waypoints = processedPlan['default_waypoints']
        self.missions.append(mission)
        self.cloud_mgr = CloudResources(slice_name="base_station")
        
        
    def update_digital_twin(self):
        """
        function call to update the digital twin with different types of incoming data   
        """
        return
    
    def handle_telemetry(self, msg):
        """
        do things like send to digital twin and ACS
        """
        if msg['type'] == "telemetry":
            print("update self coordinates")
            if msg['telemetry']['position'] is not None:
                self.droneSim.position = msg['telemetry']['position']
            if msg['telemetry']['battery'] is not None:
                self.droneSim.battery = msg['telemetry']['battery']
            #if msg['telemetry']['attitude'] is not None:
            #self.drone.attitude.pitch = msg['telemetry']['attitude']['pitch']
            #self.drone.attitude.yaw = msg['telemetry']['attitude']['yaw']
            #self.drone.attitude.roll = msg['telemetry']['attitude']['roll']
            if msg['telemetry']['heading'] is not None:
                self.droneSim.heading = msg['telemetry']['heading']
            if msg['telemetry']['home'] is not None:
                self.droneSim.home_coords.lat = msg['telemetry']['home'][0]
                self.droneSim.home_coords.lon = msg['telemetry']['home'][1]
                self.droneSim.home_coords.alt = msg['telemetry']['home'][2]

        #self.update_digital_twin(msg)
        update_acs()                                
        return

    def update_acs(self):
        postData = {}
        postData['type'] = 'Feature'
        
        geometry = {}
        geometry['type'] = 'Point'

        currentLocation = []
        currentLocation.append(self.droneSim.position.lon)
        currentLocation.append(self.droneSim.position.lat)
        currentLocation.append(self.droneSim.position.alt)

        geometry['coordinates'] = currentLocation
        postData['geometry'] = geometry
        
        properties = {}
        #just use the first mission name for now
        properties['eventName'] = self.missions[0].name
        properties['locationTimestamp'] = self.droneSim.position.time
        """
        nextWP = {}
        nextWPGeo = {}
        nextWPGeo['type'] = 'Point'
        thislon = float(nextWaypoint[0])
        thislat = float(nextWaypoint[1])
        thisheight = float(nextWaypoint[2])
        nextWaypoint[0] = thislon
        nextWaypoint[1] = thislat
        nextWaypoint[2] = thisheight
        nextWPGeo['coordinates'] = nextWaypoint
        nextWP['geometry'] = nextWPGeo
        nextWP['type'] = 'Feature'
        properties['nextWaypoint'] = nextWP
        """
        properties['userProperties'] = {}
        properties['userProperties']['heading'] = self.droneSim.heading
        postData['properties'] = properties
        post_json_data = json.dumps(postData)

        postParameters = {}
        postParameters['json'] = post_json_data
        flightupdateresp = requests.post(self.updateURL, auth=(self.usrname, self.password), data=postParameters)
        updateResp = {}
        updateResp['registrationStatusCode'] = flightupdateresp.status_code
        #print(flightsubmitresp.status_code)
        if flightupdateresp.status_code == 200:
            updateResp['registration'] = "OK"
        else:
            updateResp['registration'] = "FAILED"
        
    def basestationDispatch(self):
        UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        UDPServerSocket.bind((self.ipaddr, self.port))
        print("UDP server up and listening")

        while(True):
            msgFromServer = {}
            bytesAddressPair = UDPServerSocket.recvfrom(self.chunkSize)
            serialClientMessage = bytesAddressPair[0]
            address = bytesAddressPair[1]
            try:
                clientMessage = pickle.loads(serialClientMessage)    
                print(clientMessage['type'])
        
                recvdMsg = "Message from Drone:{}".format(clientMessage)
                clientIP  = "Drone IP Address:{}".format(address)
                print(recvdMsg)
                print(clientIP)
                recvTime = datetime.now().astimezone().isoformat()
                msgFromServer['time_received'] = recvTime
                recvUUID = clientMessage['uuid']
                msgFromServer['uuid_received'] = recvUUID
                msgType = clientMessage['type']
                msgFromServer['type_received'] = msgType

                ##############check message type from drone and decide what to do###################
                if msgType == "mission":
                    msgFromServer['missions'] = self.missions
                    
                elif msgType == "acceptMission":

                    #register in ACS  (once it's working move it down below the get resources
                    
                    """
                    ACS registration
                    """
                    print("register in ACS")
                    
                    lineString = gj.LineString(mission['default_waypoints'])
                    userProperties = {}
                    featureList = []
                    userProperties['classification'] = "scheduledFlight";
                    eventName = mission.name
                    feature = gj.Feature(geometry=lineString, properties={"eventName": eventName, "startTime": startTime, "endTime": endTime, "userProperties": userProperties, "products": [{"hazard": "MRMS_PRECIP", "parameters": [{"thresholdUnits": "inph", "comparison": ">=", "distance": 5, "distanceUnits": "miles", "threshold": 0.1}]}]})
                    featureList.append(feature)
                    fc = gj.FeatureCollection(featureList)
                    dumpFC = gj.dumps(fc, sort_keys=True)
                    FC_data = {'json': dumpFC}
                    flightsubmitresp = requests.post(self.acs, auth=(self.usrname, self.password), data=FC_data)
                    registerResp = {}
                    registerResp['registrationStatusCode'] = flightsubmitresp.status_code
                    print(flightsubmitresp.status_code)
                    if flightsubmitresp.status_code == 200:
                        registerResp['registration'] = "OK"
                    else:
                        registerResp['registration'] = "FAILED"

                    
                    #get cloud resources and configure to mission
                    """
                    print("get resources")
                    cloud_resources = self.cloud_mgr.get_resources()
                    if cloud_resources is None:
                        print("create resources")
                        status = self.cloud_mgr.create_resources()
                        print("Cloud resources status: {}".format(status))
                        cloud_resources = self.cloud_mgr.get_resources()
                    else:
                        print("Cloud resources already exist: {}".format(cloud_resources))

                    
                    #get nodes    
                    nodes = cloud_resources.get_nodes()

                    for node in nodes:
                        thisnode = resourceInfo()
                        thisnode.name = node.get_name()
                        thisnode.location = node.get_site()
                        thisnode.interface = "direct"
                        resourceAddress = ("Management IP", node.get_management_ip())
                        thisnode.resourceAddresses.append(resourceAddress)
                        thisnode.state = node.get_reservation_state()
                        print ("name: " + thisnode.name + " location: " + thisnode.location + " interface: " + thisnode.interface + " addresstype: " + resourceAddress[0] + " address: " + str(resourceAddress[1]))
                        self.resourceList.append(thisnode)
                    """
                    #configure nodes

                    """
                    Mission Library Installation on Cloud Nodes
                    """
                    """
                    #need a mapping function of mission libraries to nodes... maybe for multiple missions also
                    #for now just use the first mission and install all libraries on all nodes
                    missionLibraries = getMissionLibraries(self.missions[0])
                        
                    for node in nodes:
                        nodeName = node.get_name()
                        print("Install Libraries for nodeName: " + nodeName)
                        for library in missionLibraries:
                            libraryInstallStr = "sudo yum -y install " + library
                            print(nodeName + ": " + libraryInstallStr)
                            stdout, stderr = node.execute(libraryInstallStr)
                            print(stdout)
                            print(stderr)
                    
                    #ideally this would be coordinated be done through KubeCtl or something, but initially we'll just start up the iperf3 server in configuration
                    missionResourceCommands = getMissionResourceCommands(self.missions[0])
                    for node in nodes:
                        print("Run Commands for nodeName: " + nodeName)
                        nodeName = node.get_name()
                        for command in missionResourceCommands:
                            print("command: " + command)
                            stdout, stderr = node.execute(command)
                            print(stdout)
                            print(stderr)
                    """
                    msgFromServer['missionstatus'] = "confirmed"

                    
                elif msgType == "resourceInfo":
                    msgFromServer['resources'] = self.resourceList 
                    
                elif msgType == "telemetry":
                    #update your digital twin, update registry, pass on to downstream applications
                    self.handle_telemetry(clientMessage)
                    
                    #set command based on mission
                    print("received telemetry, asking for iperf")
                    self.currentRequests.append(self.vehicleCommands.commands['iperf']) # iperf as default            

                elif msgType == "instructionRequest":
                    msgFromServer['requests'] = self.currentRequests
                    self.currentRequests = []

                elif msgType == "iperfResults":
                    self.iperf3Agent.ipaddr = clientMessage[msgType]['ipaddr']
                    self.iperf3Agent.port = clientMessage[msgType]['port']
                    self.iperf3Agent.protocol = clientMessage[msgType]['protocol']
                    self.iperf3Agent.mbps = clientMessage[msgType]['mbps']
                    self.iperf3Agent.meanrtt = clientMessage[msgType]['meanrtt']
                    self.iperf3Agent.location4d = clientMessage[msgType]['location4d']
                    self.iperfHistory.append(self.iperf3Agent)
                    if self.iperf3Agent.mbps is not None:
                        if self.iperf3Agent.mbps > 1:
                            self.currentRequests.append(self.vehicleCommands.commands['sendVideo'])
                        else:
                            self.currentRequests.append(self.vehicleCommands.commands['flight'])
                    else:
                        self.currentRequests.append(self.vehicleCommands.commands['flight'])
                elif msgType == "sendVideo":
                    self.currentRequests.append(self.vehicleCommands.commands['flight'])
                elif msgType == "abortMission":
                    # delete the cloud resources
                    self.cloud_mgr.delete_resources()
                else:
                    print("msgType: " + msgType)
                    self.currentRequests.append(self.vehicleCommands.commands['flight'])
                try: 
                    serialMsgFromServer = pickle.dumps(msgFromServer)
                    UDPServerSocket.sendto(serialMsgFromServer, address)
                except pickle.PicklingError as pe:
                    print ("cannot encode reply msg: " + pe)
                
            except pickle.UnpicklingError as upe:
                print ("cannot decode message from drone: " + upe)
        
if __name__ == '__main__':
    FPBA = FlyPawBasestationAgent()
    FPBA.basestationDispatch()
