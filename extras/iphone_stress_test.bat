: This script tries to stress test the iphone using the test data capture script.
: The goal is to simulate a heavy two-day data collection spree (10 sessions) without any intervening dumps.
: A dump will be triggered at the the completion of all "sessions"
: Task durations are based on historical statistics as of Sept. 28, 2023
: Note: foot tapping, alternating hand movements, and sit2stand do not record on the iPhone

CALL "%NB_CONDA_INSTALL%\Scripts\activate.bat" %NB_CONDA_ENV%
CD "%NB_INSTALL%\neurobooth_os\iout"
SET DATA_OUT="D:\iphone_stress_test"

DEL /Q /S %DATA_OUT%
MKDIR %DATA_OUT%


ECHO "========== SESSION 001: 99th percentile durations =========="
SET SUBJ_ID=001
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 118
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 96
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 137
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 106
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 103
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 875
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 386
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 562
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 148
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 79
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 75
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 66
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 76
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 65
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 202


ECHO "========== SESSION 002: 50th percentile durations =========="
SET SUBJ_ID=002
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 63
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 46
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 82
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 66
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 64
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 368
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 131
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 179
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 58
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 43
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 119


ECHO "========== SESSION 003: 75th percentile durations =========="
SET SUBJ_ID=003
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 65
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 48
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 83
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 67
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 66
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 435
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 160
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 223
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 68
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 44
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 43
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 42
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 42
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 42
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 126


ECHO "========== SESSION 004: 95th percentile durations =========="
SET SUBJ_ID=004
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 79
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 61
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 91
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 75
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 70
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 623
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 230
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 393
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 103
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 69
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 75
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 66
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 76
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 65
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 202


ECHO "========== SESSION 005: 90th percentile durations =========="
SET SUBJ_ID=005
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 70
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 51
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 86
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 71
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 68
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 538
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 196
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 312
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 88
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 49
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 45
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 44
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 45
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 44
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 140


ECHO "========== SESSION 006: 50th percentile durations =========="
SET SUBJ_ID=006
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 63
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 46
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 82
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 66
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 64
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 368
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 131
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 179
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 58
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 43
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 119


ECHO "========== SESSION 007: 99th percentile durations + extra 20%  =========="
SET SUBJ_ID=007
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 142
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 115
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 164
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 128
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 124
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 1050
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 463
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 674
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 178
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 94
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 90
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 80
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 92
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 78
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 243


ECHO "========== SESSION 008: 75th percentile durations =========="
SET SUBJ_ID=008
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 65
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 48
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 83
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 67
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 66
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 435
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 160
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 223
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 68
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 44
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 43
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 42
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 42
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 42
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 126


ECHO "========== SESSION 009: 50th percentile durations =========="
SET SUBJ_ID=009
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 63
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 46
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 82
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 66
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 64
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 368
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 131
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 179
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 58
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 43
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 41
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 119


ECHO "========== SESSION 010: 90th percentile durations =========="
SET SUBJ_ID=010
: pursuit
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 70
: fixation
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 51
: gaze holding
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 86
: horiz saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 71
: vert saccades
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 68
: MOT
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 538
: DSC
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 196
: Hevelius
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 312
: passage reading
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 88
: ahh
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 49
: gogogo
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 45
: lalala
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 44
: mememe
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 45
: pataka
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 44
: finger-nose
python iphone.py --subject-id %SUBJ_ID% --recording-folder %DATA_OUT% --no-plots --duration 140


ECHO "========== Data Capture Complete---Attempting Dump =========="
CD "%NB_INSTALL%\extras"
python dump_iphone_video.py

ECHO "========== Script Completed =========="
