from neurobooth_os.iout.iphone import IPhone
import neurobooth_os.config as cfg
import re
import os
import os.path as op


def neurobooth_dump():
    
    iphone = IPhone('dump_iphone')
    iphone.prepare()
    flist = iphone.dumpall_getfilelist()

    if flist is not None:
        for fname in flist:
            sess_name = re.findall("[0-9]*_[0-9]{4}-[0-9]{2}-[0-9]{2}", fname)
            sess_folder = cfg.paths['data_out']
            
            if len(sess_name):
                sess_folder = op.join(cfg.paths['data_out'], sess_name[0])
                if not op.exists(sess_folder):
                    os.mkdir(sess_folder)
                    
            video = iphone.dump(fname)
            fname_out = op.join(sess_folder, fname)
            f = open(fname_out,'wb')
            f.write(video)
            f.close()
            iphone.dumpsuccess(fname)
            
    iphone.disconnect()
    
    
    
if __name__ == '__main__':
    import datetime 
    
    t0 = datetime.datetime.now()
    neurobooth_dump()
    print(f"total time: {datetime.datetime.now() - t0}")




