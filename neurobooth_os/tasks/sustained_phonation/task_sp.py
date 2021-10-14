from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Task


class SustainedPhonation(Task):
    def __init__(self, *args):
        super().__init__(*args)


if __name__ == "__main__":
    sts = SustainedPhonation()
    utils.run_task(sts, prompt=True)