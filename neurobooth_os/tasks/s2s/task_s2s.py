from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Task


class SitToStand(Task):
    def __init__(self, *args):
        super().__init__(*args)


if __name__ == "__main__":
    sts = SitToStand()
    utils.run_task(sts, prompt=True)