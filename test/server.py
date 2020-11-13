import eel
import json
import os

eel.init('www', ['.js', '.html', '.png', '.gif'])

@eel.expose
def get_data(results, score, outcomes):
    print(results, score, outcomes)

    # with open(os.path.join('data', file_name + '.json'), 'w', encoding='utf-8') as f:
    #     json.dump(data[1:-1], f, ensure_ascii=False, indent=4)

eel.start('DSC_simplified_oneProbe_2020.html',  cmdline_args=['--start-fullscreen', '--kisok'], size=(3840, 2160))