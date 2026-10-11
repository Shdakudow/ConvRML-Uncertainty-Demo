import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from scripts.quantile_search_calibration import select_pair,select_fixed_sequence,upper_risk_bound

class QuantileCalibrationTests(unittest.TestCase):
    def test_confidence_penalty(self):
        self.assertGreater(upper_risk_bound(.04,2048,.001),upper_risk_bound(.04,2048,.025))
        self.assertGreater(upper_risk_bound(.04,2048,.001),.04)
    def test_selects_width_and_asymmetric_risk_not_q_gap(self):
        lo=np.tile([.001,.012,.08],(2048,1));hi=np.tile([.12,.02,.001],(2048,1))
        r=select_pair(lo,hi,[.05,.2,.3],[.4,.6,.9],lower_q=[.001,.2,.4],upper_q=[.55,.8,.99])
        self.assertEqual((r['lower_q'],r['upper_q']),(.2,.8))
        self.assertLessEqual(r['total_risk_ucb'],.1)
        self.assertAlmostEqual(r['calibration_width'],.4)
    def test_refuses_uncertified_pair(self):
        with self.assertRaisesRegex(ValueError,'No quantile pair'):
            select_pair(np.full((2048,1),.2),np.full((2048,1),.2),[.1],[.9],lower_q=[.1],upper_q=[.9])
    def test_single_pair_still_has_two_tail_budget(self):
        r=select_pair(np.zeros((2048,1)),np.zeros((2048,1)),[.1],[.9],lower_q=[.02],upper_q=[.97])
        self.assertEqual(r['per_candidate_delta'],.025)
    def test_fixed_sequence_stops_even_if_later_candidate_passes(self):
        lo=np.tile([.001,.2,.001],(2048,1));hi=np.tile([.001,.2,.001],(2048,1))
        r=select_fixed_sequence(lo,hi,[.1,.2,.3],[.6,.7,.8],lower_q=[.01,.02,.03],upper_q=[.95,.97,.99])
        self.assertEqual((r['lower_q'],r['upper_q']),(.01,.99))
        self.assertEqual([len(t) for t in r['traces']],[2,2])

if __name__=='__main__':unittest.main()
