# video writer
# * writes frames at a fixed rate even if camera's rate varies or is imprecise,
#  possibly dropping or repeating frames in the process
#  (note: for LifeCam, the frame rate depends on the exposure)
# * also writes trajectories (which need to be in sync with frames written)
# * stop() needs to be called at the end of video, unless VideoWriter is
#  instantiated with "with"
# code comes from
# Ulrich Stern
# https://github.com/ulrichstern/SkinnerTrax/blob/master/rt-trx/rt-trx.py
# modified by Matias Andina 2020-02-01

import queue
import threading
import cv2
import time
import numpy as np

class VideoWriter:

  _EXT = ".avi"

  # note: extension ".avi" will be added to given video filename
  def __init__(self, filename=None, fps=90.0, resolution = (1280, 720)):
    self.filename = filename 
    self.empty_filename = filename is None
    if self.empty_filename:
      return
    print ("\nwriting video to %s" %filename)

    self.fourcc = cv2.VideoWriter_fourcc(*'XVID')
    self.fps = fps
    self.dt = 1.0/fps
    self.resolution = resolution
    # We will put frames on a queue and get them from there
    self.q = queue.Queue()
    self._stop = False
    # n is the frame number
    self.n = 0 
    self.wrtr = threading.Thread(target=self.recorder)
    self.wrtr.start()

  # writer thread
  def recorder(self):
    # initialize things to None
    # we will receive tuples, lastframe_ts has the frame and timestamp
    lastframe_ts = t0 = video_writer = None
    while True:
      if self._stop:
        break
      frame_ts = lastframe_ts
      # while we have frames in queue get most recent frame
      while not self.q.empty():
        # get queue as tupple
        frame_ts = self.q.get_nowait()
      # only do things with frames that are not None
      if frame_ts is not None:
        lastframe_ts = frame_ts
        # unpack
        frame, ts = frame_ts
        if video_writer is None:
          # initialize cv2 video_writer
          video_writer = cv2.VideoWriter(self.filename + self._EXT,
            self.fourcc,
            self.fps,
            self.resolution,
            isColor= self.is_color(frame))
          t0 = time.time()
        # write frame
        video_writer.write(frame)
        # write timestamp
        self.write_timestamp(timestamp=ts)
        self.n += 1
      if t0 is None:
        dt = self.dt
      else:
        dt = max(0, t0 + self.n * self.dt - time.time())
      # this will put the thread to sleep to satisfy frame rate
      time.sleep(dt)

  # for "with"
  def __enter__(self): return self
  def __exit__(self, exc_type, exc_value, traceback):
    if not self.empty_filename and not self._stop:
      self.stop()

  # write frame; can be called at rate different from fps
  def put_to_q(self, frame, timestamp):
    if not self.empty_filename:
      # put frame and timestamp as tupple into queue
      self.q.put((frame, timestamp))


  # returns number (0,1,...) of next frame written to video; None if no video
  # written
  def frameNum(self): return None if self.empty_filename else self.n

  # returns the video filename (without extension), None if no video written
  def filename(self): return self.filename

  # stop video writer
  def stop(self):
    if not self.empty_filename:
      self._stop = True
      self.wrtr.join()

  def is_color(self, frame):
    if (len(frame.shape) == 3):
      return True
    else:
      return False

  def write_timestamp(self, timestamp):
    timestamp = timestamp.strftime('%Y-%m-%d_%H:%M:%S:%f')
    # this will write timestamps to file
    # mind that timestamp must be in a [] for numpy to like it
    with open(self.filename + "_timestamp.csv",'a') as outfile:
      np.savetxt(outfile, [timestamp],
      delimiter=',', fmt='%s')
      
VW = VideoWriter('test.avi')

VW._stop
