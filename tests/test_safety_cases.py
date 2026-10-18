import pytest

from eval.safety_eval import check_case, load_cases


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["name"])
def test_malicious_boundary(case, database):
    result = check_case(case, database)
    assert result["passed"], result
