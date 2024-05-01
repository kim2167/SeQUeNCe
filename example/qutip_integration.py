# import qutip as qtp
from qutip import basis, identity, sigmax, sigmaz, tensor, bell_state, measure_povm
from qutip_qip.operations import hadamard_transform, cnot, swap
import numpy as np
import sequence as sqnc
from sequence.resource_management.memory_manager import MemoryManager 


# Ad hoc generation of 3-qubit GHZ state from 2 BDS
# we assume all 1-qubit gates are perfect, only 1-qubit measurements and multi-qubit gates are noisy
# before performing GHZ generation, BDS from SeQUeNCe simulation must check their memories' last_update_time, to make sure that all idling decoherence is included

def bell_dm(state, elem_order):
    """Function to create BDS density matrix as QuTiP Qobj instance.

    4 Bell states: Phi+ (|00>+|11>), Phi- (|00>-|11>), Psi+ (|01>+|10>), Psi- (|01>-|10>) are ordered as 0,1,2,3.
    Will use bell_state() function inside QuTiP.
    
    Args:
        state (array): 1-d array of 4 BDS density matrix diagonal elements.
        elem_order (List[int]): the indices of corresponding Bell states for the 4 BDS density matrix diagonal elements.

    Return:
        bell_dm (Qobj): BDS density matrix as QuTiP Qobj.
    """

    bell_dm = 0  # initialization

    for elem, idx in zip(state, elem_order):
        idx_str = format(idx, 'b')  # transform Bell state index into binary strings for bell_state() function in QuTiP
        pure_bell_dm = bell_state(idx_str) * bell_state(idx_str).dag()
        bell_dm += elem * pure_bell_dm

    return bell_dm


def noisy_meas(fid):
    """Function to create a 2-element POVM correponding to a noisy 1-qubit measurement.

    Modeled as a mixture of correct and incorrect projectors.

    Arg:
        fid (float): fidelity of the noisy measurement, equal to the probability of correct projector in the mixture.
    
    Return:
        noisy_meas (List[Qobj])
    """

    povm_0 = fid * basis(2,0) * basis(2,0).dag() + (1-fid) * basis(2,1) * basis(2,1).dag()
    povm_1 = fid * basis(2,1) * basis(2,1).dag() + (1-fid) * basis(2,0) * basis(2,0).dag()

    return [povm_0, povm_1]


def merge(state1, state2, cnot_fid, meas_fid):
    """Ad hoc function to generate a 3-qubit GHZ state from 2 BDS using imperfect GHZ merging, 
        where noisy CNOT is modeled as a mixture of noiseless CNOT and 2-qubit completely depolarizing channel.

    Input states should be QuTiP quantum objects (density matrix). 
    BDS should have major component as (|00> + |11>)/\sqrt{2}.

    Args:
        state1 (Qobj): first BDS density matrix.
        state2 (Qobj): second BDS density matrix.
        cnot_fid (float): fidelity of noisy CNOT gate.
        meas_fid (float): fidelity of noisy 1-qubit measurement.
    
    Return
        ghz_state (Qobj): generated GHZ state.
    """

    bell_dm_1 = bell_dm(state1)
    bell_dm_2 = bell_dm(state2)
    init_state = tensor(bell_dm_1, bell_dm_2)  # initial state as tensor product of two BDS, qubits are labeled 0,1,2,3

    # apply CNOT between two BDS, control on qubit 1 and target on qubit 2
    cnot_12 = tensor(identity(2), cnot(), identity(2))  # noiseless CNOT unitary
    swap_12 = tensor(identity(2), swap(), identity(2))
    swap_23 = tensor(identity(4), swap())
    post_cnot_state = cnot_fid * cnot_12 * init_state * cnot_12.dag()\
          + (1-cnot_fid) * swap_23 * swap_12 * (tensor(init_state.ptrace([0,3]),identity(4))/4) * swap_12.dag() * swap_23.dag()

    # apply noisy measurement, assuming on qubit 1
    povm0, povm1 = noisy_meas(meas_fid)  # 1-qubit povms
    povm0 = tensor(identity(2), povm0, identity(4))
    povm1 = tensor(identity(2), povm1, identity(4))
    povms = [povm0, povm1]
    res, post_meas_state = measure_povm(post_cnot_state, povms)

    # trace out qubit 1
    post_meas_state.ptrace([0,1,2])
    # apply feedforward X correction on qubit 0 if measure result is 1 (now remaining qubit 0, 1, 2)
    if res == 0:
        ghz_state = post_meas_state
    if res == 1:
        x_gate = tensor(sigmax(),identity(4))
        ghz_state = x_gate * post_meas_state * x_gate.dag()

    return ghz_state


def gate_teleport(state1, state2, cnot_fid, meas_fid):
    """Ad hoc function to generate a 3-qubit GHZ state from 2 BDS using imperfect CNOT teleportation, 
        where noisy CNOT is modeled as a mixture of noiseless CNOT and 2-qubit completely depolarizing channel.

    Input states should be QuTiP quantum objects (density matrix). 
    BDS should have major component as (|01> + |10>)/\sqrt{2}. 
    Following derivation in (Chou, Kevin S., et al. "Deterministic teleportation of a quantum gate between two logical qubits." Nature 561.7723 (2018): 368-373.)
    We assume center qubit (control) is initialized in |+> state, and other two qubits (targets) are initialized in |0> state.

    Args:
        state1 (Qobj): first BDS density matrix.
        state2 (Qobj): second BDS density matrix.
        cnot_fid (float): fidelity of noisy CNOT gate.
        meas_fid (float): fidelity of noisy 1-qubit measurement.
    
    Return
        ghz_state (Qobj): generated GHZ state.
    """

    bell_dm_1 = bell_dm(state1)
    bell_dm_2 = bell_dm(state2)

    povm0, povm1 = noisy_meas(meas_fid)  # 1-qubit povms

    plus_state = (basis(2,0) + basis(2,1)) / np.sqrt(2)
    plus_dm = plus_state * plus_state.dag()
    zero_dm = basis(2,0) * basis(2,0).dag()

    ### 1st teleported CNOT
    init_state = tensor(plus_dm, bell_dm_1, zero_dm)

    cnot_01 = tensor(cnot(), identity(4))
    cnot_23 = tensor(identity(4), cnot())
    cnot_01_23 = cnot_01 * cnot_23

    state_both_succ = cnot_01_23 * init_state * cnot_01_23.dag()
    state_01_succ = tensor((cnot_01 * init_state * cnot_01.dag()).ptrace([0,1]), identity(4)/4)
    state_23_succ = tensor(identity(4)/4, (cnot_23 * init_state * cnot_23.dag()).ptrace([2,3]))
    state_both_fail = tensor(identity(4)/4, identity(4)/4)

    post_cnot_state = cnot_fid**2 * state_both_succ + cnot_fid * (state_01_succ + state_23_succ) + (1-cnot_fid)**2 * state_both_fail

    # measure qubit 1 in Z basis
    # full povms for qubit 1 (measure in Z basis)
    povm0_1 = tensor(identity(2), povm0, identity(4))
    povm1_1 = tensor(identity(2), povm1, identity(4))
    povms_1 = [povm0_1, povm1_1]

    res1, post_meas1_state = measure_povm(post_cnot_state, povms_1)

    # measure qubit 2 in X basis
    # full povms for qubit 2 (measure in X basis, thus need Hadamard gate prior to meas)
    povm0_2 = tensor(identity(4), povm0, identity(2))
    povm1_2 = tensor(identity(4), povm1, identity(2))
    povms_2 = [povm0_2, povm1_2]

    hadamard_2 = tensor(identity(4), hadamard_transform(), identity(2))
    post_meas1_state = hadamard_2 * post_meas1_state * hadamard_2.dag()

    res2, post_meas2_state = measure_povm(post_meas1_state, povms_2)

    # trace out qubits 1 and 2
    post_meas_state = post_meas2_state.ptrace([0,3])
    # apply feedforward Z correction on qubit 0 if qubit 2 measurement result is 1
    # apply feedforward X correction on qubit 3 if qubit 1 measurement result is 1
    x_gate = tensor(identity(2), sigmax())
    z_gate = tensor(sigmaz(), identity(2))
    if res1 == 0 and res2 == 0:
        final_state = post_meas_state
    elif res1 == 1 and res2 == 0:
        final_state = x_gate * post_meas_state * x_gate.dag()
    elif res1 == 0 and res2 == 1:
        final_state = z_gate * post_meas_state * z_gate.dag()
    elif res1 == 1 and res2 == 1:
        final_state = z_gate * x_gate * post_meas_state * x_gate.dag() * z_gate.dag()
    
    ### 2nd teleported CNOT
    # previously the center qubit is indexed 0
    # now we swap it to qubit 1, so that it can be a direct neighbor of the second BDS, and serve as the control again
    final_state = swap() * final_state * swap().dag()
    init_state = tensor(final_state, bell_dm_2, zero_dm)

    cnot_12 = tensor(identity(2), cnot(), identity(4))
    cnot_34 = tensor(identity(8), cnot())
    cnot_12_34 = cnot_12 * cnot_34

    state_both_succ = cnot_12_34 * init_state * cnot_12_34.dag()
    state_12_succ = tensor((cnot_12 * init_state * cnot_12.dag()).ptrace([0,1,2]), identity(4)/4)
    state_34_succ = tensor(identity(4)/4, (cnot_34 * init_state * cnot_34.dag()).ptrace([0,3,4]))
    # swap current qubits 0, 1, 2 to 1, 2, 0 (first 1 <-> 2, then 0 <-> 1)
    swap_01 = tensor(swap(), identity(8))
    swap_12 = tensor(identity(2), swap(), identity(2))
    state_34_succ = swap_01 * swap_12 * state_34_succ * swap_12.dag() * swap_01.dag()
    state_both_fail = tensor(init_state.ptrace([0]), identity(4)/4, identity(4)/4)

    post_cnot_state = cnot_fid**2 * state_both_succ + cnot_fid * (state_12_succ + state_34_succ) + (1-cnot_fid)**2 * state_both_fail

    # measure qubit 2 in Z basis
    # full povms for qubit 2 (measure in Z basis)
    povm0_2 = tensor(identity(4), povm0, identity(4))
    povm1_2 = tensor(identity(4), povm1, identity(4))
    povms_2 = [povm0_2, povm1_2]

    res2, post_meas2_state = measure_povm(post_cnot_state, povms_2)

    # measure qubit 3 in X basis
    # full povms for qubit 3 (measure in X basis, thus need Hadamard gate prior to meas)
    povm0_3 = tensor(identity(4), povm0, identity(2))
    povm1_3 = tensor(identity(4), povm1, identity(2))
    povms_3 = [povm0_3, povm1_3]

    hadamard_3 = tensor(identity(8), hadamard_transform(), identity(2))
    post_meas1_state = hadamard_3 * post_meas2_state * hadamard_3.dag()

    res3, post_meas2_state = measure_povm(post_meas2_state, povms_3)

    # trace out qubits 2 and 3
    post_meas_state = post_meas2_state.ptrace([0,1,4])
    # apply feedforward Z correction on qubit 1 if qubit 3 measurement result is 1
    # apply feedforward X correction on qubit 4 if qubit 2 measurement result is 1
    x_gate = tensor(identity(4), sigmax())
    z_gate = tensor(identity(2), sigmaz(), identity(2))
    if res2 == 0 and res3 == 0:
        ghz_state = post_meas_state
    elif res2 == 1 and res3 == 0:
        ghz_state = x_gate * post_meas_state * x_gate.dag()
    elif res2 == 0 and res3 == 1:
        ghz_state = z_gate * post_meas_state * z_gate.dag()
    elif res2 == 1 and res3 == 1:
        ghz_state = z_gate * x_gate * post_meas_state * x_gate.dag() * z_gate.dag()

    return ghz_state


class AppQutipInt:
    def __init__(self, mem_manager: MemoryManager) -> None:
        '''Args:
            mem_manager (MemoryManager): manages all the memories'''
        self.mem_manager=mem_manager

    def start(self) -> None:
        pass

    def get_memory(self, mem_info):
        '''Starts the operations on the bell state.
        Args: 
            mem_info (resource_management.memory_manager.MemoryInfo): '''
        #TODO: "Alvin: I'm not sure what method will determine the memory state."
        state="ENTANGLED"
        self.mem_manager.update(mem_info.memory, state)

    def bds_to_qobj(self, bell_st):
        '''Converts bell_st to qutip qobj.
        Args: 
            bell_st (np.ndarray) : 
        Returns: qtp.qobj'''
        # return qtp.Qobj(bell_st)  
        #TODO: has been redone, QuTiP has computational basis as default, thus need basis transformation

        pass
        

    def start_decoherence(self):
        '''Asynch process that modifies stored qobj with decoherence.'''
        pass


if __name__ == "__main__":
    # Start application.
    # Sequence stuff to init.
    mem_manager=[]
    app = AppQutipInt(mem_manager)
    app.start()
    # Get from sequence.
    # mem_info=[]
    # app.get_memory(mem_info)

    # # Get from sequence.
    # bell_st=[] 
    # app.bds_to_qobj(bell_st)

    # app.start_decoherence()
    # #Begin gate teleporation.

    # Tests
    state=np.array([[0,1],[1,0]])
    print(state)
    print(app.bds_to_qobj(state))