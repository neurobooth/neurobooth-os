from typing import List, Optional
from random import randint, Random
import numpy as np
from neurobooth_os.tasks.task import Eyelink_HostPC


class SDMT(Eyelink_HostPC):
    def __init__(self, symbols: List[str], seed: Optional[int], cell_size: (float, float), grid: (int, int), **kwargs):
        super().__init__(**kwargs)

        self.symbols = np.array(symbols, dtype='U1')
        self.cell_size: (float, float) = cell_size
        self.grid: (int, int) = grid
        self.seed: int = seed if (seed is not None) else randint(0, 1<<20)
        self.rng = Random(self.seed)
        self.test_sequence = self.generate_test_sequence()

    def generate_test_sequence(self) -> np.ndarray:
        h, w = self.grid
        seq = np.full(h*w, ' ', dtype='U1')
        seq[0] = self.rng.choice(self.symbols)
        for i in range(h*w-1):
            seq[i+1] = self.rng.choice(np.setdiff1d(self.symbols, seq[i]))  # No back-to-back symbols
        return seq.reshape(self.grid)
