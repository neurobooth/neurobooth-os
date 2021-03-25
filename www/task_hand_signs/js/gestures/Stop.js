import { Finger, FingerCurl, FingerDirection } from '../FingerDescription';
import GestureDescription from '../GestureDescription';


// describe stop gesture ✋
const stopDescription = new GestureDescription('stop');


// thumb:
stopDescription.addCurl(Finger.Thumb, FingerCurl.NoCurl, 1.0);

// index:
stopDescription.addCurl(Finger.Index, FingerCurl.NoCurl, 1.0);
stopDescription.addDirection(Finger.Index, FingerDirection.VerticalUp, 1.0);

// middle:
stopDescription.addCurl(Finger.Middle, FingerCurl.NoCurl, 1.0);

// ring:
stopDescription.addCurl(Finger.Ring, FingerCurl.NoCurl, 1.0);


// pinky:
stopDescription.addCurl(Finger.Pinky, FingerCurl.NoCurl, 1.0);


// give additional weight to index and ring fingers
//stopDescription.setWeight(Finger.Index, 2);
//stopDescription.setWeight(Finger.Thumb, 2);

export default stopDescription;
