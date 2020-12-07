import { Finger, FingerCurl, FingerDirection } from '../FingerDescription';
import GestureDescription from '../GestureDescription';


// describe stop gesture ✋
const stopDescription = new GestureDescription('stop');


// thumb:
stopDescription.addCurl(Finger.Thumb, FingerCurl.NoCurl, 1.0);

// index:
stopDescription.addCurl(Finger.Index, FingerCurl.NoCurl, 1.0);

// middle:
stopDescription.addCurl(Finger.Middle, FingerCurl.NoCurl, 1.0);

// ring:
stopDescription.addCurl(Finger.Ring, FingerCurl.NoCurl, 1.0);


// pinky:
stopDescription.addCurl(Finger.Pinky, FingerCurl.NoCurl, 1.0);



export default stopDescription;
