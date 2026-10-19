from eval.metrics import prf


def test_prf():
    result = prf(8, 2, 4)
    assert round(result["precision"], 4) == 0.8
    assert round(result["recall"], 4) == 0.6667
    assert round(result["f1"], 4) == 0.7273
