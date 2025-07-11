# This file should eventually contain common device types, such as base class defining the lifecycle.
# For now, it is just the frame preview interface.

from typing import ByteString


class CameraPreviewException(Exception):
    """An exception raised when unable to capture a preview image/frame from a camera stream."""
    pass


class CameraPreviewer:
    def frame_preview(self) -> ByteString:
        """
        Retrieve a single frame from a camera.

        :returns: The raw data of the image/frame, or an empty byte string if an error occurs.
        """
        raise NotImplementedError()
