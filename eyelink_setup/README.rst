How to setup the network configuration for the Eyelink eyetracker
=================================================================
This doc gives an overview of the network design of the neurobooth and explains how to set up the network configuration on the Eyelink eyetracker NUC so that network communication works correctly.

The Eyelink eyetracker consists of a NUC (which is a small pocket computer), an eyetracking camera, and a tablet with the Eyelink app on it. The NUC broadcasts wifi which the tablet connects to, and the Eyelink app on the tablet can be used to see what the camera is seeing, and hence position the camera, adjust focus etc.

The primary DHCP server on the neurobooth network is a linux machine (neurodoor), which is responsible for assigning IP addresses to other devices on the network, including CTR/ACQ/STM, NAS, and the NUC.

The NUC has two NICs (network interface controllers), one each for WiFi and Ethernet, both of these NICs run a DHCP server on them, and will try to assign IPs to devices connected on the same network as them. Additionally, in the version of eyetracker that we use, there is an internal bridge between the WiFi and Ethernet NIC, such that a communication will be forwarded from one NIC to the other internally. All of these facts mean that there is a direct conflict of the NUC with the DHCP server on neurodoor.

To fix these issues we need to configure the NUC so as to:

1. Disable the DHCP server on the Ethernet NIC
2. Break the internal bridge between the WiFi and Ethernet NIC

The network diagram and the solution can be visualized in the following network diagram:


.. image:: NetworkDiagram.png
    :align: center

Steps to set up the EyeLink eyetracker
======================================

Initial Setup
-------------
1. Set up the EyeLink eyetracker as per the user manual
2. You should be able to connect the tablet to the eyetracker and see the camera output in the Eyelink app
3. Tap "Dashboard", and then tap "Connections", the Eyelink app will show you the "Host IP" - this is the IP address of the WiFi NIC on the NUC. You will see the IP as 192.168.100.1 as this is the IP that is configured from the factory. This is problem because neurodoor DHCP server is also configured at 192.168.100.1 and there is a direct conflict between the subnets of the two DHCP servers.

Changing the "Host IP" of the NUC's WiFi NIC
--------------------------------------------
1. To change the IP of the WiFi NIC, connect a monitor and keyboard to the NUC, restart the NUC by clicking the "Reboot" option on the tablet, otherwise long press the one physical button on the NUC to power off the NUC, and press it again once to power ON the NUC.
2. When the NUC boots, use the keyboard arros keys to select the "boot in headless mode" option and press enter - the NUC will boot in the command line interface mode.
3. You can use linux commands to traverse the directory tree, you will be in root, and the relevant files are in the "elcl" folder. Do ``cd /elcl/exe`` and do an ``ls``. You will see a file called ``start_tk``
4. This files runs everytime the NUC boots, and holds the network configuration details for the NUC.










 
