#from neurobooth_os.iout.iphone import IPhone
from neurobooth_os.iout.iphone_boston_apr1 import IPhone
import neurobooth_os.config as cfg


def neurobooth_dump():
    
    pdir = cfg.paths['data_out']
    
    
    
    
    
if __name__ == '__main__':
    #fname="iphone_test_video_1"
    iphone = IPhone('dump_iphone')
    iphone.prepare()
    flist = iphone.dumpall_getfilelist()
    print("\n"+str(flist))
    
    if flist is not None:
        for fname in flist:
            
            #if len(fname.split("_")) >
            
            #sess_folder = ''
            video = iphone.dump(fname)
            f = open(fname,'wb')
            f.write(video)
            f.close()
            iphone.dumpsuccess(fname)
            
    iphone.disconnect()

    #11_2022-03-22_22h-07m-14s_mock_task_1
