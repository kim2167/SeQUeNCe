import numpy

from sequence.kernel.timeline import Timeline
from sequence.components.photon import Photon


numpy.random.seed(0)


def test_init():
    tl = Timeline()
    photon = Photon("", tl)
    
    assert photon.quantum_state.state == (complex(1), complex(0))


def test_entangle():
    tl = Timeline()
    photon1 = Photon("p1", tl)
    photon2 = Photon("p2", tl)
    photon1.entangle(photon2)

    state1 = photon1.quantum_state
    state2 = photon2.quantum_state

    test_state = (complex(1), complex(0), complex(0), complex(0))
    for i, coeff in enumerate(state1.state):
        assert coeff == state2.state[i]
        assert coeff == test_state[i]
    assert state1.entangled_states == state2.entangled_states
    assert state1.entangled_states == [state1, state2]


def test_set_state():
    tl = Timeline()
    photon = Photon("", tl)
    test_state = (complex(0), complex(1))
    photon.set_state(test_state)

    for i, coeff in enumerate(photon.quantum_state.state):
        assert coeff == test_state[i]


def test_measure():
    tl = Timeline()
    photon1 = Photon("p1", tl, quantum_state=(complex(1), complex(0)))
    photon2 = Photon("p2", tl, quantum_state=(complex(0), complex(1)))
    basis = ((complex(1), complex(0)), (complex(0), complex(1)))

    assert Photon.measure(basis, photon1) == 0
    assert Photon.measure(basis, photon2) == 1


def test_measure_multiple():
    tl = Timeline()
    photon1 = Photon("p1", tl)
    photon2 = Photon("p2", tl)
    photon1.entangle(photon2)

    basis = ((complex(1), complex(0), complex(0), complex(0)),
             (complex(0), complex(1), complex(0), complex(0)),
             (complex(0), complex(0), complex(1), complex(0)),
             (complex(0), complex(0), complex(0), complex(1)))

    assert Photon.measure_multiple(basis, [photon1, photon2]) == 0
