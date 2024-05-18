from queue import PriorityQueue
from threading import Thread
from typing import Any, List

from pydantic import BaseModel

"""
    Manage a priority queue of work to be processed

    Design overview:
    Use a thread-safe PriorityQueue on CTR to maintain a queue of "request" objects. The requests will be 
    sent from CTR to the other servers (mostly STM).
    
    Request Types:
    Most of the requests will be "Present" requests, one for each psychopy task to be executed. 
    Other request types include: Connect, Prepare, Terminate, Pause, Continue, End Session
    
    Note: The Present Task requests may be subdivided into several steps. For example, instead of having STM message CTR
    to setup LSL streaming, STM may respond to a PrepareTask request when all prior steps are complete, and CTR will 
    setup the threads and then send a new message stating that STM should proceed with processing the current task.
    This would enable a somewhat simpler messaging model where most of the requests are going in one direction.
    
    CTR Processing Model:
    CTR will receive requests from the GUI based on user actions. The actions include basic session setup 
    (choosing the study and subject, for example) and requests related to running the psychopy session. The former 
    are handled on CTR, while the later require interactions with the other servers. 
    
    For items requiring interaction with the other servers, CTR will maintain a request priority queue operated using 
    a Producer/Consumer model, with FastAPI managing the producer side, and a separate ConsumerThread picking items 
    off the queue to control the operations of the other servers. 
    
    Assuming a similar startup process (initialize, connect, start), The user will press the connect button, 
    for example, and CTR will create a new ConnectDevicesRequest that it will put on the PriorityQueue. If the 
    ConsumerThread is not busy, it will pick up the request and forward it to the other servers. 
    
    To maintain the proper sequence, the Consumer side will have only one worker thread, and requests sent to the other
    servers will be handled synchronously. When all devices are connected (or retries exhausted) STM and ACQ will send 
    back a response. When both responses are received, the ConsumerThread waits for more work.
    
    TODO: How do we handle these multi-server messages?
    
    
    
    
    A separate RequestConsumer t
    
"""


class PrioritizedRequest(BaseModel):
    priority: int
    request: Any

    def __eq__(self, other):
        return isinstance(other, PrioritizedRequest) and self.priority == other.priority

    def __lt__(self, other):
        return isinstance(other, PrioritizedRequest) and self.priority < other.priority


req_queue = PriorityQueue()


def build_initial_queue(task_list: List[str]):
    index = 10
    for task in task_list:
        req_1 = PrioritizedRequest(priority=1000 + index, request=task)
        print(req_1)
        req_queue.put(req_1)
        index = index + 10


def replace_queue(q: PriorityQueue, replacement: PrioritizedRequest):
    print("clearing and replacing")
    # TODO: This should be done with a mutex, but it keeps deadlocking when using with q.mutex...
    while not q.empty():
        q.get(False)
        q.task_done()
    print("queue is clear")
    q.put(replacement)


def main():
    tasks = ['calibrate', 'h_saccades', 'v_saccades', 'go', 'la', 'pad', 'finger']
    build_initial_queue(tasks)
    print(tasks)
    p_consumer = PriorityConsumer(req_queue)
    p_consumer.start()


class ProducerThread(Thread):
    def run(self):
        pass


class PriorityConsumer(Thread):
    tasks_out = []

    def __init__(self, q: PriorityQueue):
        super(PriorityConsumer, self).__init__()
        self.q: PriorityQueue = q

    def process(self, x):
        if self.q.qsize() == 3:
            t = PrioritizedRequest(priority=0, request="Terminate")
            # TODO: Can we use a flag that causes an exit from the queue processing loop
            #       so we don't have to clear the queue?
            replace_queue(self.q, t)

        print(x)
        self.tasks_out.append(x.request)
        print(self.tasks_out)
        self.q.task_done()
        print(self.q.empty())

    def run(self):
        while not self.q.empty():
            x = self.q.get()
            self.process(x)


if __name__ == '__main__':
    main()
