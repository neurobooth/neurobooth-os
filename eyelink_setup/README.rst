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
3. Tap "Dashboard", and then tap "Connections", the Eyelink app will show you the "Host IP" - this is the IP address of the WiFi NIC on the NUC. You will see the IP as 192.168.100.1 as this is the IP that is configured from the factory. This is a problem because the neurodoor DHCP server is also configured at 192.168.100.1 and there is a direct conflict between the subnets of the two DHCP servers.

Changing the "Host IP" of the NUC's WiFi NIC
--------------------------------------------
1. To change the IP of the WiFi NIC, connect a monitor and keyboard to the NUC, restart the NUC by clicking the "Reboot" option on the tablet, otherwise long press the one physical button on the NUC to power off the NUC, and press it again once to power ON the NUC.
2. When the NUC boots, use the keyboard arrow keys to select the "boot in headless mode" option and press enter - the NUC will boot in the command line interface mode.
3. You can use linux commands to traverse the directory tree, you will be in root, and the relevant files are in the "elcl" folder. Do ``cd /elcl/exe`` and do an ``ls``. You will see a file called ``start_tk``
4. This file runs everytime the NUC boots, and holds the network configuration details for the NUC. Change the HOST_WIFI_IP parameter in line 247 to ``HOST_WIFI_IP="192.168.100.15"`` you can use VI to make this edit in the start_tk file. Save the change and restart the NUC.
5. Check that the host WiFi has changed by opening the Eyelink app on the tablet, and tapping "Connections" to confirm that Host IP value - it should show 192.168.100.15

Disabling Ethernet DHCP server on NUC
-------------------------------------
1. Connect a Windows computer using a LAN cable to an unmanaged switch. When you do an ``ipconfig`` on the Windows machine, you will see an IP in the range 169.254.X.Y, this is the default range that Windows computers use when they are connected to an unmanaged network.
2. Connect the NUC using a LAN cable to the same unmanaged switch. Because the NUC is running a DHCP server (on both its WiFi and Ethernet NICs) the NUC will attempt to assign an IP address to the Windows machine. Confirm that the IP of the Windows machine has changed by running ``ipconfig``, it should be different from 169.254.X.Y. In all likelyhood the IP will be in the range of 10.1.1.X, which is the subnet used by the Ethernet NIC as configured from the factory.
3. In case there is no update in the Windows machine's IP, try a few things:

  * power cycle the switch - OR
  * Take out both cables from the switch, confirm Windows is still on 169.254.X.Y, connect NUC to switch, after a short wait (30s) connect Windows, wait for two minutes then check Windows ip again via ipconfig - OR
  * Do an ``ipconfig /release`` followed by an ``ipconfig /renew`` on Windows - OR
  * Disable the ethernet adapter in Windows, then enable it again after 30s - OR
  * Reboot the NUC - OR
  * Any combination of the above till Windows is assigned an IP by any dhcp server in the NUC

4. In case you see that Windows has an IP in the range of 192.168.100.X - that is also ok, this means that Windows has been assigned an IP by the dhcp server on the WiFi NIC in NUC.
5. Now that Windows has an IP assigned by NUC, you can access the NUC's filesystem via a WebUI that is provided by the NUC. For this open any web browser and put in the IP address of the dhcp server that has assigned IP to the Windows machine - meaning if Windows has a 10.1.1.X IP, type in 10.1.1.1 in the browser, if its 192.168.100.X, type in 192.168.100.15 (remember we set this as host IP in previous step for WiFi NIC) in the browser. This should open the NUC's WebUI.
6. Next, click on the "gear" ICON and go into settings, then click on the "network" icon to open the network configuration page (the icon looks like a tiny flow diagram), this opens the Configuration.html window of the WebUI
7. Tick the "Disable Ethernet DHCPD" check box. Leave all other options as default. This disables the DHCP server running on the Ethernet NIC of the NUC.
8. Repeat all of the steps above, and you will see that Windows now only ever gets a 192.168.100.X IP, because the only DHCP server active in the NUC is on the WiFi NIC. 

An image of line 247 on start_tk and the Configuration.html page of NUC's WebUI is pasted below:

.. image:: HOST_WIFI_IP_and_Configuration_options.jpg.png
    :align: center









 
