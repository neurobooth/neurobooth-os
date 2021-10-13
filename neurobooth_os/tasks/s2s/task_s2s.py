from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Base_Task


class SitToStand(Base_Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


if __name__ == "__main__":
    sts = SitToStand()
    utils.run_task(sts, prompt=True)