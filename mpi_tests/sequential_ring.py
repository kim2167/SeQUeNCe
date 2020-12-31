from sequence.kernel.timeline import Timeline
from sequence.kernel.quantum_manager_server import kill_server
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.components.optical_channel import ClassicalChannel, \
    QuantumChannel
from sequence.app.random_request import RandomRequestApp
import sequence.utils.log as log

from json import dump
import os
import pandas as pd
from time import time


def ring_network(ring_size: int, lookahead: int, stop_time: int,
                 log_path: str):
    tick = time()
    if not os.path.exists(log_path):
        os.mkdir(log_path)

    CC_DELAY = 1e9
    MEMO_SIZE = 50
    RAW_FIDELITY = 0.99

    tl = Timeline(stop_time=stop_time)

    routers = []
    bsm_nodes = []
    router_names = []
    for node_id in range(ring_size):
        node_name = "Node_%d" % node_id
        router_names.append(node_name)

        node = QuantumRouter(node_name, tl, MEMO_SIZE)
        node.set_seed(node_id)
        node.memory_array.update_memory_params('raw_fidelity',
                                               RAW_FIDELITY)
        routers.append(node)

    for bsm_id in range(ring_size):
        node_name = "BSM_%d" % bsm_id
        pre_node_name = 'Node_%d' % ((bsm_id - 1) % ring_size)
        post_node_name = 'Node_%d' % bsm_id

        node = BSMNode(node_name, tl, [pre_node_name, post_node_name])
        node.set_seed(ring_size + bsm_id)
        bsm_nodes.append(node)

    for src in routers + bsm_nodes:
        for dst_index in range(ring_size):
            dst_name = "Node_%d" % dst_index
            if dst_name != src.name:
                cc = ClassicalChannel("cc_%s_%s" % (src.name, dst_name),
                                      tl, 20000, CC_DELAY // 2)
                cc.set_ends(src, dst_name)

            dst_name = "BSM_%d" % dst_index
            if dst_name != src.name:
                cc = ClassicalChannel("cc_%s_%s" % (src.name, dst_name),
                                      tl, 20000, CC_DELAY // 2)
                cc.set_ends(src, dst_name)

    for src in routers:
        bsm_index = int(src.name.replace("Node_", ""))
        bsm_name = "BSM_%d" % bsm_index
        qc = QuantumChannel("qc_%s_%s" % (src.name, bsm_name),
                            tl, 0.0002, lookahead * 2e-4)
        qc.set_ends(src, bsm_name)
        router_name = "Node_%d" % ((bsm_index + 1) % ring_size)
        src.add_bsm_node(bsm_name, router_name)

        bsm_name = "BSM_%d" % ((bsm_index - 1) % ring_size)
        qc = QuantumChannel("qc_%s_%s" % (src.name, bsm_name),
                            tl, 0.0002, lookahead * 2e-4)
        qc.set_ends(src, bsm_name)
        router_name = "Node_%d" % ((bsm_index - 1) % ring_size)
        src.add_bsm_node(bsm_name, router_name)

    for node in routers:
        node_index = int(node.name.replace("Node_", ""))
        for dst in router_names:
            if node.name != dst:
                dst_index = int(dst.replace("Node_", ""))
                if abs(node_index - dst_index) < ring_size - abs(
                        node_index - dst_index):
                    if dst_index > node_index:
                        bsm_name = "Node_%d" % ((node_index + 1) % ring_size)
                    else:
                        bsm_name = "Node_%d" % ((node_index - 1) % ring_size)
                else:
                    if dst_index > node_index:
                        bsm_name = "Node_%d" % ((node_index - 1) % ring_size)
                    else:
                        bsm_name = "Node_%d" % ((node_index + 1) % ring_size)

                node.network_manager.protocol_stack[0].add_forwarding_rule(dst,
                                                                           bsm_name)

        # for dst in node.network_manager.protocol_stack[0].forwarding_table:
        #     print(node.name, '->', dst, node.network_manager.protocol_stack[0].forwarding_table[dst])

    apps = []
    for i, node in enumerate(routers):
        seed = int(node.name.replace("Node_", ""))
        app_node_name = node.name
        others = router_names[:]
        others.remove(app_node_name)
        app = RandomRequestApp(node, others, seed, 1e13, 2e13, 10, 25, 0.8,
                               1.0)
        apps.append(app)
        app.start()

    tl.init()

    prepare_time = time() - tick

    tick = time()
    tl.run()
    execution_time = time() - tick

    print(tl.now(), len(tl.events))

    # write network information into log_path/net_info.json file
    net_info = {'topology': 'ring', 'size': ring_size,
                'lookahead': lookahead,
                'stop_time': stop_time,
                'CC_delay': CC_DELAY, 'QC_delay': lookahead * 2e-4,
                'memory_array_size': MEMO_SIZE,
                'initial_fidelity': RAW_FIDELITY,
                "execution_time": execution_time,
                "prepare_time": prepare_time}
    with open(log_path + '/net_info.json', 'w') as fh:
        dump(net_info, fh)

    # write reservation information into log_path/traffic_RANK.csv file
    initiators = []
    responders = []
    start_times = []
    end_times = []
    memory_sizes = []
    fidelities = []
    paths = []
    wait_times = []
    throughputs = []
    for node in routers:
        initiator = node.name
        reserves = node.app.reserves
        _wait_times = node.app.get_wait_time()
        _throughputs = node.app.get_throughput()
        min_size = min(len(reserves), len(_wait_times), len(_throughputs))
        reserves = reserves[:min_size]
        _wait_times = _wait_times[:min_size]
        _throughputs = _throughputs[:min_size]
        for reservation, path, wait_time, throughput in zip(reserves,
                                                            node.app.paths,
                                                            _wait_times,
                                                            _throughputs):
            responder, s_t, e_t, size, fidelity = reservation
            initiators.append(initiator)
            responders.append(responder)
            start_times.append(s_t)
            end_times.append(e_t)
            memory_sizes.append(size)
            fidelities.append(fidelity)
            paths.append(path)
            wait_times.append(wait_time)
            throughputs.append(throughput)
    traffic_info = {"Initiator": initiators, "Responder": responders,
                    "Start_time": start_times, "End_time": end_times,
                    "Memory_size": memory_sizes, "Fidelity": fidelities,
                    "Path": paths, "Wait_time": wait_times,
                    "Throughput": throughputs}

    df = pd.DataFrame(traffic_info)
    df.to_csv(log_path + "/traffic.csv")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='The example of sequential quantum network')
    parser.add_argument('ring_size', type=int, help='the size of ring network')
    parser.add_argument('lookahead', type=int,
                        help='the lookahead of parallel simulation (ps); the longer lookahead generate the longer quantum channel')
    parser.add_argument('stop_time', type=int,
                        help='the time of stopping the simulation (sec)')
    parser.add_argument('log_path', type=str,
                        help='the path of log files')

    args = parser.parse_args()

    print('Simulate {}-node ring network {} sec sequentially'.format(
        args.ring_size, args.stop_time))

    ring_network(args.ring_size, args.lookahead, args.stop_time * 1e12,
                 args.log_path)