import pyxdf
import matplotlib.pyplot as plt
import numpy as np

file = r'C:\neurobooth\neurobooth_data\sz2__DSC_task.xdf'
data, header = pyxdf.load_xdf(file)



for ix, stream in enumerate(data):

    print("Stream {}: {} - type {} - shape {} at {} Hz (effective {} Hz)".format(
        ix + 1, stream['info']['name'][0],
        stream['info']['type'][0],
        (int(stream['info']['channel_count'][0]), len(stream['time_stamps'])),
        round(float(stream['info']['nominal_srate'][0]), 2),
        round(float(stream['info']['effective_srate'])), 2)
    )

    if any(stream['time_stamps']):
        print("\tDuration: {:.2f} s".format(stream['time_stamps'][-1] - stream['time_stamps'][0]))



for ix, stream in enumerate(data):
    print("\t",stream['info']['name'][0])

    desc, = stream['info']['desc']
    if desc is None:
        continue
    for k, v in desc.items():
        print(k, v)
    # print(desc[0])

    # add real fps
    #to json

plt.figure()
for i, d in enumerate(data):
    name = d['info']['name']
    if d['time_stamps'].size == 0 :
        print(f"{name} samples:0")
        continue
    ts1, = d['footer']['info']['last_timestamp']
    ts0, = d['footer']['info']['first_timestamp']
    # ts0 = d['time_stamps'][2]
    # ts1 = d['time_stamps'][-1]
    tsn, = d['footer']['info']['sample_count']
    duration = float(ts1)-float(ts0)
    fps = 0 if int(tsn)==0 else int(tsn)/duration

    print(f"{name} samples:{tsn}, duration: {duration}, fps:{fps}")

    tmst = d['time_stamps']
    plt.plot(tmst, [i]*len(tmst), ".", label=name)

plt.legend()


fig, ax = plt.subplots(1,2)
n = 4
tdiff = np.diff(data[n]['time_stamps'])
ax[0].plot(tdiff)
ax[0].set_title("ff")
ax[1].hist(np.diff(data[n]['time_stamps']), 25)


fig, ax = plt.subplots(1,2)
n =  4
ts = np.array([ float(s[0]) for s in data[n]['time_series']])
ts = np.diff(ts)
ax[0].plot(ts)
ax[0].set_title("ff")
ax[1].hist(ts, 25)


plt.figure()
tt = data[n]['time_stamps']
ts = np.array([ float(s[0]) for s in data[n]['time_series']])
plt.scatter(tt, ts)


ts = [ float(s[0]) for s in data[n]['time_series']]
ts = [t - ts[0] for t in ts]

tt = data[n]['time_stamps']
tt -= tt[0]
plt.figure()
tdf = ts - tt
plt.plot(tdf)

plt.figure()
plt.plot(tt)
plt.plot(ts)


ts = np.array([ float(s[0]) for s in data[n]['time_series']])
ts = np.diff(ts)

tt = np.diff(data[n]['time_stamps'])
plt.figure()
tdf = ts - tt
plt.plot(tdf)

plt.figure()
tdf = ts - tt
plt.plot(ts)
plt.plot(tt)


plt.figure()
for i, d in enumerate(data):
    name = d['info']['name']

    fig, ax = plt.subplots(1,2)
    tdiff = np.diff(d['time_stamps'])
    ax[0].plot(tdiff)
    ax[0].set_title(name)
    ax[1].hist(np.diff(d['time_stamps']))

    if d['time_stamps'].size == 0 :
        print(f"{name} samples:0")
        continue
    ts1, = d['footer']['info']['last_timestamp']
    ts0, = d['footer']['info']['first_timestamp']
    # ts0 = d['time_stamps'][2]
    # ts1 = d['time_stamps'][-1]
    tsn, = d['footer']['info']['sample_count']
    duration = float(ts1)-float(ts0)
    fps = 0 if int(tsn)==0 else int(tsn)/duration

    print(f"{name} samples:{tsn}, duration: {duration}, fps:{fps}")

    tmst = d['time_stamps']
    plt.plot(tmst, [i]*len(tmst), ".", label=name)

plt.legend()


## Plot time series



plt.figure()
for i, d in enumerate(data):
    name = d['info']['name']
    if name != ['Audio']:
        continue
    if d['time_stamps'].size == 0 :
        print(f"{name} samples:0")
        continue

    tt = d['time_stamps']
    ts = d['time_series']

    if isinstance(ts, list):
        ts = np.array(ts)

    ts_f = ts.flatten("C")
    plt.plot(ts_f, label=name)

plt.legend()




plt.figure()
for i, d in enumerate(data):
    name = d['info']['name']

    fig, ax = plt.subplots(1,1)
    tdiff = np.diff(d['time_stamps'])
    ax.plot(tdiff)
    ax.set_title(name)


    if d['time_stamps'].size == 0 :
        print(f"{name} samples:0")
        continue
    ts1, = d['footer']['info']['last_timestamp']
    ts0, = d['footer']['info']['first_timestamp']
    # ts0 = d['time_stamps'][2]
    # ts1 = d['time_stamps'][-1]
    tsn, = d['footer']['info']['sample_count']
    duration = float(ts1)-float(ts0)
    fps = 0 if int(tsn)==0 else int(tsn)/duration

    print(f"{name} samples:{tsn}, duration: {duration}, fps:{fps}")

    tmst = d['time_stamps']
    # plt.plot(tmst, [i]*len(tmst), ".", label=name)

plt.legend()

n = 2
plt.figure()
plt.hist(1/np.diff(data[n]['time_stamps']), 25)


# plot audio + markers
plt.legend()
d = data[0]
name = d['info']['name']

tt = d['time_stamps']
ts = d['time_series']
ts = [0]*10
plt.plot(tt,ts, "*", label=name)
ts = [0.5]*10
plt.plot(tt,ts, "*", label=name)
plt.plot(tt,ts, "-", label=name)
plt.axvline(tt,ts)
plt.axvline(tt)
tt
plt.vlines([tt])

plt.vlines(tt,0, 1, "red")

plt.figure()
n=0
d = data[n]
tt = d['time_stamps']
name = d['info']['name']
plt.vlines(tt,0, 1)

for i, d in enumerate(data):
    name = d['info']['name']
    print(name)
    if name != ['Audio']:
        continue
    if d['time_stamps'].size == 0 :
        print(f"{name} samples:0")
        continue

    tt = d['time_stamps']
    ts = d['time_series']

    if isinstance(ts, list):
        ts = np.array(ts)

    ts = ts.max(1)
    # ts_f = ts.flatten("C")
    plt.plot(tt,ts, color="r", label=name)
