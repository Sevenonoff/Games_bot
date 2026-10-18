"""Прогон текстовых сценариев из tests/scenarios/*.scenario — каждый отдельным тестом."""
import pytest

from tests.scenario import ScenarioFailed, load_all, run

SCENARIOS = load_all()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[sc.id for sc in SCENARIOS])
async def test_scenario(scenario):
    try:
        await run(scenario)
    except ScenarioFailed as e:
        if scenario.draft and not scenario.error:
            pytest.xfail("черновик: фича ещё не готова")
        pytest.fail(str(e), pytrace=False)
    if scenario.draft:
        pytest.fail(f"«{scenario.name}» уже проходит — снимите метку @черновик", pytrace=False)


def test_scenarios_found():
    assert SCENARIOS, "в tests/scenarios нет ни одного сценария"
