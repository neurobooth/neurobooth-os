How to setup the network configuration for the Eyelink eyetracker
=================================================================
This doc gives an overview of the network design of the neurobooth and explains how to set up the network configuration on the Eyelink eyetracker NUC so that network communication works correctly.

The Eyelink eyetracker consists of a NUC (which is a small pocket computer), an eyetracking camera, and a tablet with the Eyelink app on it. The NUC broadcasts wifi which the tablet connects to, and the Eyelink app on the tablet can be used to see what the camera is seeing, and hence position the camera, adjust focus etc.

The primary DHCP server on the neurobooth network is a linux machine (neurodoor), which is responsible for assigning IP addresses to other devices on the network, including CTR/ACQ/STM, NAS, and the NUC.

The NUC has two NICs (network interface controllers), one each for WiFi and Ethernet, both of these NICs run a DHCP server on them, and will try to assign IPs to devices connected on the same network as them. Additionally, in the version of eyetracker that we use, there is an internal bridge between the WiFi and Ethernet NIC, such that a communication will be forwarded from one NIC to the other internally. All of these facts mean that there is a direct conflict of the NUC with the DHCP server on neurodoor.

This can be visualized in the following network diagram:
![Alt text](./NetworkDiagram.png?raw=true "Network Diagram")
