
import PySpin
import matplotlib.pyplot as plt
import numpy as np
import time
import os
import cv2
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"




def vect_2_image_array(pyspin_image, color=True):
    chans = 3 if color == True else 1
    width = pyspin_image.GetWidth()
    height = pyspin_image.GetHeight()
    img_array = pyspin_image.GetData()
    img_array = img_array.reshape(height, width, chans)
    return img_array
    


serial = '20522874' #Probably different for you although I also use a cam USB3.0
system = PySpin.System.GetInstance()
cam_list = system.GetCameras()
cam = cam_list.GetBySerial(serial)


# nodemap = cam.GetTLDeviceNodeMap()
# node_pixel_format = PySpin.CEnumerationPtr(nodemap.GetNode('PixelFormat'))
# if PySpin.IsAvailable(node_pixel_format) and PySpin.IsWritable(node_pixel_format):
#     node_pixel_format_mono8 = PySpin.CEnumEntryPtr(node_pixel_format.GetEntryByName('BayerBG8'))
# #height = cam.Height()
# #width = cam.Width()
# cam.PixelFormat.SetValue(PySpin.AdcBitDepth_Bit8)

cam.Init()
cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)

cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)

exposure = 4500
gain = 20
gamma = .6

cam.ExposureTime.SetValue(exposure)
cam.Gamma.SetValue(gamma)
cam.Gain.SetValue(gain)
cam.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Once)
cam.BalanceWhiteAuto.SetValue(0)




cam.BeginAcquisition()
nFrames = 1000

image_queue = []

stamp = []
for _ in range(nFrames):
    im = cam.GetNextImage(1000)
    ts = im.GetTimeStamp()
    # im_conv = im.Convert(PySpin.PixelFormat_BGR8, PySpin.HQ_LINEAR)
    # im_conv_d = im_conv.GetData()
    
    image_queue.append(im.GetData())
 #   stamp.append(time.time_ns())
    stamp.append(ts)
    
    #  Release image
    #
    #  *** NOTES ***
    #  Images retrieved directly from the camera (i.e. non-converted
    #  images) need to be released in order to keep from filling the
    #  buffer.
    im.Release()


print((np.diff(stamp).mean()/1e6))

print(1000/(np.diff(stamp).mean()/1e6))

plt.plot(np.array(stamp)/1e6)

plt.figure()
plt.plot(np.diff(stamp)/1e6)

cam.EndAcquisition() 


cam.DeInit()


cv2.namedWindow("output", cv2.WINDOW_NORMAL)     

im = im_conv
proc_im = np.array(im.GetData(), dtype="uint8").reshape( (im.GetHeight(), im.GetWidth(), 3) );
plt.figure()
for img in image_queue[::1]:
    proc_im = np.array(img, dtype="uint8").reshape( (im.GetHeight(), im.GetWidth()) );
    cv2.imshow("output", proc_im)
    cv2.waitKey(0)
    
    # plt.imshow(proc_im)
    # plt.show()
    # plt.pause(.005)
    
cv2.imshow("output", proc_im)


plt.figure()
plt.plot(np.diff(stamp)/1e6)
plt.ylabel("time diff in ms")

plt.figure()
plt.hist(np.diff(stamp)/1e6)
plt.xlabel("time diff in ms")
plt.show()




import cv2
import EasyPySpin

cap = EasyPySpin.VideoCapture(0)
ret, frame = cap.read()

frame_bgr = cv2.demosaicing(frame, cv2.COLOR_BayerBG2BGR) # The second argument may need to be changed depending on your sensor.

cv2.imshow("output", frame_bgr)

    
cap.release()

