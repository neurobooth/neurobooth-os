import pyxdf
import matplotlib.pyplot as plt
import numpy as np

file = r'C:\Users\neurobooth\Desktop\neurobooth\software\neurobooth_data\test__mouse_task.xdf'
data, header = pyxdf.load_xdf(file)



for ix, stream in enumerate(data):

    print("Stream {}: {} - type {} - uid {} - shape {} at {} Hz (effective {} Hz)".format(
        ix + 1, stream['info']['name'][0],
        stream['info']['type'][0],
        stream['info']['uid'][0],
        (int(stream['info']['channel_count'][0]), len(stream['time_stamps'])),
        stream['info']['nominal_srate'][0],
        stream['info']['effective_srate'])
    )

    if any(stream['time_stamps']):
        print("\tDuration: {} s".format(stream['time_stamps'][-1] - stream['time_stamps'][0]))


    y = stream['time_series']

    if isinstance(y, list):
        # list of strings, draw one vertical line for each marker
        for timestamp, marker in zip(stream['time_stamps'], y):
            plt.axvline(x=timestamp)
            print(f'Marker "{marker[0]}" @ {timestamp:.2f}s')
    elif isinstance(y, np.ndarray):
        # numeric data, draw as lines
        if np.size(y) != 0:
            plt.plot(stream['time_stamps'], y)
    else:
        raise RuntimeError('Unknown stream format')

plt.show()



for i, d in enumerate(data):
    name = d['info']['name']
    ts1, = d['footer']['info']['last_timestamp']
    ts0, = d['footer']['info']['first_timestamp']
    tsn, = d['footer']['info']['sample_count']
    duration = float(ts1)-float(ts0)
    fps = 0 if int(tsn)==0 else int(tsn)/duration
    
    print(f"{name} samples:{tsn}, duration: {duration}, fps:{fps}")

    tmst = d['time_stamps']
    plt.plot(tmst, [i]*len(tmst), ".", label=name)

plt.legend()
