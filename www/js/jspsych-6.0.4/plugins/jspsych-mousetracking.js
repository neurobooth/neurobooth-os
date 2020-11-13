/**
 * jspsych-html-button-response
 * Josh de Leeuw
 *
 * plugin for displaying a stimulus and getting a keyboard response
 *
 * documentation: docs.jspsych.org
 *
 **/

jsPsych.plugins["mousetracking"] = (function() {

  var plugin = {};

  plugin.info = {
    name: 'html-button-response-pmatching',
    description: '',
    parameters: {
      stimulus: {
        type: jsPsych.plugins.parameterType.HTML_STRING,
        pretty_name: 'Stimulus',
        default: undefined,
        description: 'Trial stimulus-- can be image or string'
      },
      stimulus_size: {
        type: jsPsych.plugins.parameterType.INT,
        pretty_name: 'image sizes',
        default: [150, 150],
        description: "Width and height of the images that need to be chosen. Default is 40x40."
      },
      choices: {
        type: jsPsych.plugins.parameterType.STRING,
        pretty_name: 'Choices',
        default: undefined,
        array: true,
        description: 'The images to be displayed-- can be image or string.'
      },
      trial_duration: {
        type: jsPsych.plugins.parameterType.INT,
        pretty_name: 'Trial duration',
        default: null,
        description: 'How long to show the trial.'
      },
      container_size: {
        type: jsPsych.plugins.parameterType.INT,
        pretty_name: 'Mousetracking container size',
        default: [1000, 600],
        description: "Width and height of the container size within which the mousetracking will occur. Default is 1100x800 size sinze 4x3 is the typical computer screen size."
      },
      time_res: {
        type: jsPsych.plugins.parameterType.INT,
        pretty_name: 'Mousetracking time resolution',
        default: 20,
        description: "After how many miliseconds should x-y coordinates be sampled? If time_dim is 20, X and Y coordinates of the mouse will be sampled every 20 miliseconds. This is essentially the time resolution of mouse tracking."
      }
    }
  }

  plugin.trial = function(display_element, trial) {

    var cont_width = trial.container_size[0]
    var cont_height = trial.container_size[1]

    // display stimulus
    display_element.innerHTML += '<div id="mousetracking-container" style= "border:2px solid transparent; border-color: #ccc; position: relative; width:' + cont_width+ 'px; height:' + cont_height+ 'px"></div>';

    var paper = display_element.querySelector("#mousetracking-container");

    //display buttons
  //  paper.innerHTML += '<div id="jspsych-html-button-response-btngroup">';
    paper.innerHTML += '<div id="jspsych-mousetracking-btngroup">';
    var str = trial.choices[0]
    paper.innerHTML +=  '<div class="jspsych-btn-fb" style="display: inline-block; position: absolute; top:20px; right:20px; width: 100px; height:40px" id="mousetracking-button-' + 0 +'" data-choice="'+0+'">'+str+'</div>';
    var str = trial.choices[1]
    paper.innerHTML +=  '<div class="jspsych-btn-fb" style="display: inline-block; position: absolute; top:20px; left:20px; width: 100px; height:40px" id="mousetracking-button-' + 1 +'" data-choice="'+1+'">'+str+'</div>';
    paper.innerHTML += '</div>';

    paper.innerHTML += '<div id="jspsych-mousetracking-stimulus" style = " position: absolute; bottom:'+ (cont_height - trial.stimulus_size[1])/2 +'px; left:'+ (cont_width - trial.stimulus_size[0])/2 +'px"><img style="width:'+trial.stimulus_size[0]+'px; height:'+trial.stimulus_size[0]+'px" src = "'+trial.stimulus+'"/img></div>';

    // start time
    var start_time = Date.now();


XmousePos = []
YmousePos = []
time = []
numMouse=0
var m_pos_x,m_pos_y;
window.onmousemove = function(e) { m_pos_x = Math.round(e.pageX-$(paper).offset().left); m_pos_y = Math.round(e.pageY-$(paper).offset().top); }
XmousePos.push(m_pos_x)
YmousePos.push(m_pos_y)
time.push(Date.now()-start_time)
var mouseInterval = setInterval(function() {
      XmousePos.push(m_pos_x)
      YmousePos.push(m_pos_y)
      time.push(Date.now()-start_time)
      numMouse+=1
    },
    trial.time_res);


//
    // add event listeners to buttons
    for (var i = 0; i < trial.choices.length; i++) {
      display_element.querySelector('#mousetracking-button-' + i).addEventListener('click', function(e){
        var choice = e.currentTarget.getAttribute('data-choice'); // don't use dataset for jsdom compatibility
        after_response(choice);
      });
    }

    // store response
    var response = {
      rt: null,
      button: null
    };

    // function to handle responses by the subject
    function after_response(choice) {
      // measure rt
      var end_time = Date.now();
      var rt = end_time - start_time;
      response.button = choice;
      response.rt = rt;
    //  console.log(response.button)

    //  console.log(XmousePos, YmousePos, time)

      // after a valid response, the stimulus will have the CSS class 'responded'
      // which can be used to provide visual feedback that a response was recorded
      display_element.querySelector('#jspsych-mousetracking-stimulus').className += ' responded';

      // disable all the buttons after a response
      var btns = document.querySelectorAll('.mousetracking-button button');
      for(var i=0; i<btns.length; i++){
        //btns[i].removeEventListener('click');
        btns[i].setAttribute('disabled', 'disabled');
      }
      end_trial();
    };

    // function to end trial when it is time
    function end_trial() {

      // kill any remaining setTimeout handlers
      jsPsych.pluginAPI.clearAllTimeouts();

      clearInterval(mouseInterval)

      // gather the data to store for the trial
      var trial_data = {
        "rt": response.rt,
        "stimulus": trial.stimulus,
        "button_pressed": response.button,
        "x-position": XmousePos,
        "y-position": YmousePos,
        "mice-times": time,
        "nRecordings": numMouse
      };

      // clear the display
      display_element.innerHTML = '';

      // move on to the next trial
      jsPsych.finishTrial(trial_data);
    };

    // end trial if time limit is set
    if (trial.trial_duration !== null) {
      jsPsych.pluginAPI.setTimeout(function() {
        end_trial();
      }, trial.trial_duration);
    }

  };

  return plugin;
})();
