import { Finger, FingerCurl, FingerDirection } from '../FingerDescription';
import GestureDescription from '../GestureDescription';


// describe OK gesture 👌
const OKDescription = new GestureDescription('OK');


// thumb:
OKDescription.addCurl(Finger.Thumb, FingerCurl.HalfCurl, 1.0);
OKDescription.addCurl(Finger.Thumb, FingerCurl.FullCurl, 1.0);
OKDescription.addCurl(Finger.Thumb, FingerCurl.NoCurl, 1.0);
//OKDescription.addDirection(Finger.Thumb, FingerDirection.DiagonalUpLeft, 1);
//OKDescription.addDirection(Finger.Thumb, FingerDirection.HorizontalLeft, .5);
//OKDescription.addDirection(Finger.Thumb, FingerDirection.DiagonalUpRight, 1);
//OKDescription.addDirection(Finger.Thumb, FingerDirection.HorizontalRight, .5);

// index:
OKDescription.addCurl(Finger.Index, FingerCurl.HalfCurl, 1.0);
OKDescription.addCurl(Finger.Index, FingerCurl.FullCurl, 1.0);
//OKDescription.addDirection(Finger.Index, FingerDirection.DiagonalUpLeft, 1);
//OKDescription.addDirection(Finger.Index, FingerDirection.HorizontalLeft, .2);
//OKDescription.addDirection(Finger.Index, FingerDirection.DiagonalUpRight, 1);
//OKDescription.addDirection(Finger.Index, FingerDirection.HorizontalRight, .2);

// middle:
OKDescription.addCurl(Finger.Middle, FingerCurl.NoCurl, 1.0);
OKDescription.addDirection(Finger.Middle, FingerDirection.VerticalUp, 1.0);

// ring:
OKDescription.addCurl(Finger.Ring, FingerCurl.NoCurl, 1.0);
//OKDescription.addDirection(Finger.Ring, FingerDirection.VerticalUp, 0.2);

// pinky:
OKDescription.addCurl(Finger.Pinky, FingerCurl.NoCurl, 1.0);
//OKDescription.addDirection(Finger.Pinky, FingerDirection.VerticalUp, 0.2);

// give additional weight to index and ring fingers
OKDescription.setWeight(Finger.Index, 2);
OKDescription.setWeight(Finger.Thumb, 2);

export default OKDescription;
