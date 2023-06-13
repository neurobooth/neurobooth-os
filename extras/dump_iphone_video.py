import neurobooth_os.iout.iphone as iphone
import neurobooth_os.config as cfg
import re
import os
import os.path as op
import datetime
import logging
from neurobooth_os.logging import make_iphone_dump_logger


def neurobooth_dump():
    session_root = cfg.paths["data_out"]
    logger = logging.getLogger('iphone_dump')
    logger.debug(f'Session Root: {session_root}')

    logger.debug('Connecting to iPhone')
    phone = iphone.IPhone("dump_iphone")
    handshake_success = phone.prepare()
    if not handshake_success:
        logger.error(f'Unable to connect to iPhone [state={phone._state}]!')
        return

    flist = phone.dumpall_getfilelist()
    if flist is None:
        logger.error(f'Unable to retrieve file list [state={phone._state}]!')
        phone.disconnect()
        return

    logger.debug(f'Files to transfer: {str(flist)}')
    for fname in flist:
        sess_name = re.findall("[0-9]*_[0-9]{4}-[0-9]{2}-[0-9]{2}", fname)
        if len(sess_name) == 0 or sess_name is None:
            logger.error(f'Invalid session name: file={fname}; name={sess_name}.')
            continue

        sess_folder = op.join(session_root, sess_name[0])
        if not op.exists(sess_folder):
            logger.debug(f'Creating directory: {sess_folder}')
            os.mkdir(sess_folder)

        dump_file(phone, fname, op.join(sess_folder, fname))

    logger.debug('Disconnecting iPhone')
    phone.disconnect()


def dump_file(phone: iphone.IPhone, fname: str, fname_out: str) -> None:
    logger = logging.getLogger('iphone_dump')
    if op.exists(fname_out):
        logger.error(f'Cannot write {fname_out} as it already exists!')
        return

    logger.info(f'Dump {fname} -> {fname_out}')
    file_data = phone.dump(fname)
    if len(file_data) == 0:
        logger.error(f'{fname} returned a zero-byte file!')
        return

    with open(fname_out, "wb") as f:
        f.write(file_data)
    logger.debug(f'Wrote {fname_out}, {len(file_data)/(1<<20):0.1f} MiB')

    phone.dumpsuccess(fname)
    logger.debug(f'Sent @DUMPSUCCESS for {fname}')


if __name__ == "__main__":
    logger = make_iphone_dump_logger()
    iphone.DEBUG_IPHONE = 'verbatim_no_lsl'

    t0 = datetime.datetime.now()
    logger.info('Running Dump')
    neurobooth_dump()
    logger.info(f"Dump Complete; Total Time: {datetime.datetime.now() - t0}")
