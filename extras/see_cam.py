# -*- coding: utf-8 -*-
"""
This script allows viewing an image from an attached camera.
"""

import cv2


NUMBER_KEYS = {ord(str(d)): d for d in range(10)}
QUIT_KEYS = [ord('q'), ord('Q'), 27]  # 27 is ASCII for escape


def main() -> None:
    print("Press a number key to change the camera feed. Press 'q' or Escape to quit.")

    camera_idx = 0
    old_camera_idx = camera_idx
    cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)

    while True:
        ret, frame = cap.read()
        if ret:
            frame = cv2.putText(  # Write the camera index to the frame
                frame, f'Camera {camera_idx}', (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 1, cv2.LINE_AA
            )
            cv2.imshow(f"Camera Feed", frame)
        elif old_camera_idx != camera_idx:
            print(f"No camera {camera_idx}! Reverting to camera {old_camera_idx}.")
            camera_idx = old_camera_idx
            cap.release()
            cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)

        key = cv2.waitKey(1)
        if key in QUIT_KEYS:
            break
        elif key in NUMBER_KEYS:
            old_camera_idx = camera_idx
            camera_idx = NUMBER_KEYS[key]
            cap.release()
            cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)

    # When everything done, release the capture
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
