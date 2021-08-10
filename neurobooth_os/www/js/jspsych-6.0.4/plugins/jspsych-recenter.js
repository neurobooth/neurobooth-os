/**
 * jspsych-html-button-response
 * Josh de Leeuw
 *
 * plugin for displaying a stimulus and getting a keyboard response
 *
 * documentation: docs.jspsych.org
 *
 **/

jsPsych.plugins["recenter"] = (function() {

  var plugin = {};

  plugin.info = {
    name: 'pregame',
    description: '',
    parameters: {
      stimulus_duration: {
        type: jsPsych.plugins.parameterType.INT,
        pretty_name: 'Stimulus duration',
        default: null,
        description: 'How long to hide the stimulus.'
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
      }
    }
  }


  plugin.trial = function(display_element, trial) {

    var cont_width = trial.container_size[0]
    var cont_height = trial.container_size[1]

    display_element.innerHTML += '<div id="pmatching-container" style= "border:2px solid transparent; border-color: #ccc; position: relative; width:'+cont_width+'px; height:'+cont_height+'px"></div>';
    var paper = display_element.querySelector("#pmatching-container");

    paper.innerHTML += '<div class="jspsych-btn-fb" style="position:absolute; bottom:10px; left:'+(cont_width-100)/2+'px; height: 40px; width: 80px" id="jspsych-html-button-response-button-0" data-choice="cont">Next</div>';
    var start_time = Date.now();

    // add event listeners to buttons
    for (var i = 0; i <1; i++) {
      display_element.querySelector('#jspsych-html-button-response-button-' + i).addEventListener('click', function(e){
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


      // disable all the buttons after a response
      var btns = document.querySelectorAll('.jspsych-html-button-response-button button');
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

      // gather the data to store for the trial
      var trial_data = {
        "rt": response.rt,
        "stimulus": trial.stimulus,
        "button_pressed": response.button
      };

      // clear the display
      display_element.innerHTML = '';

      // move on to the next trial
      jsPsych.finishTrial(trial_data);
    };

    // hide image if timing is set
    if (trial.stimulus_duration !== null) {
      jsPsych.pluginAPI.setTimeout(function() {
        display_element.querySelector('#jspsych-html-button-response-stimulus').style.visibility = 'hidden';
      }, trial.stimulus_duration);
    }

    // end trial if time limit is set
    if (trial.trial_duration !== null) {
      jsPsych.pluginAPI.setTimeout(function() {
        end_trial();
      }, trial.trial_duration);
    }

  };

  return plugin;
})();
