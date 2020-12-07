//Holds the Handpose model object
let model;
//Holds the context object of the canvas
let ctx;
let video = document.getElementById("videoElement");
let canvas = document.getElementById("canvasElement");
  
const motherImg = document.getElementById("mother");
const fatherImg = document.getElementById("father");
const brotherImg = document.getElementById("brother");
const sisterImg = document.getElementById("sister");
const babyImg = document.getElementById("baby");

//landmarks is an array of 3D coordinates predicted by the Handpose model
function displayImagesAtFingerTop(landmarks) {
    for (let i = 0; i < landmarks.length; i++) {
        const y = landmarks[i][0];
        const x = landmarks[i][1];
        if(i == 4) {
            ctx.drawImage(fatherImg, y-15, x-40, 30, 60);
        } else if(i == 8) {
            ctx.drawImage(motherImg, y-15, x-40, 30, 60);
        } else if(i == 12) {
            ctx.drawImage(brotherImg, y-15, x-40, 30, 60);
        } else if(i == 16) {
            ctx.drawImage(sisterImg, y-15, x-40, 30, 60);
        } else if(i == 20) {
            ctx.drawImage(babyImg, y-15, x-40, 30, 60);
        }  
    }
}

async function predict() {    
    //Draw the frames obtained from video stream on a canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
     
    //Predict landmarks in hand (3D coordinates) in the frame of a video
    const predictions = await model.estimateHands(video);
    if(predictions.length > 0) {
        const landmarks = predictions[0].landmarks;
        displayImagesAtFingerTop(landmarks);
    }
  
    requestAnimationFrame(predict);
}

async function main() {
    //Load the Handpose model
    model = await handpose.load();
  
    //Start the video stream, assign it to the video element and play it
    if(navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({video: true})
            .then(stream => {
                //assign the video stream to the video element
                video.srcObject = stream;
                //start playing the video
                video.play();
            })
            .catch(e => {
                console.log("Error Occurred in getting the video stream");
            });
    }
  
    video.onloadedmetadata = () => {
        //Get the 2D graphics context from the canvas element
        ctx = canvas.getContext('2d');
        //Reset the point (0,0) to a given point
        ctx.translate(canvas.width, 0);
        //Flip the context horizontally
        ctx.scale(-1, 1);
  
        //Start the prediction indefinitely on the video stream
        requestAnimationFrame(predict);
    };   
}