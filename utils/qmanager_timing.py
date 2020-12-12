import time
import multiprocessing
import numpy as np

from sequence.kernel.quantum_manager_server import generate_arg_parser, start_server, QuantumManagerMessage, QuantumManagerMsgType
from sequence.kernel.quantum_manager_client import QuantumManagerClient
from sequence.components.circuit import Circuit


def client_function(ip, port):
    client = QuantumManagerClient(ip, port)
    client.init()

    # send request for new state
    key = client.new()

    # send request to get state
    ket_vec = client.get(key)

    # run Hadamard gate
    circ = Circuit(1)
    circ.h(0)
    client.run_circuit(circ, [key])

    # get state again to verify
    ket_vec = client.get(key)

    # disconnect
    client.close()


NUM_TRIALS = 3
NUM_CLIENTS = 100

parser = generate_arg_parser()
args = parser.parse_args()

p = multiprocessing.Process(target=start_server, args=(args.ip, args.port))
p.start()

times = []
for _ in range(NUM_TRIALS):
    start = time.time()
    pool = multiprocessing.Pool(NUM_CLIENTS, client_function, [args.ip, args.port])
    pool.close()
    pool.join()
    end = time.time()
    print("\ttime:", end - start)
    times.append(end - start)

# close server
kill_client = QuantumManagerClient(args.ip, args.port)
kill_client.kill()

print("average time:", np.mean(times))

