"""A championship of teams, and one of players, rendered in this process.

The competitor type is chosen once, at creation, and every tab then
speaks of teams or of players: the controls of one are not offered for
the other.
"""

import re
from collections.abc import Iterator

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser
from litestar.testing import TestClient

from data.championship.championship_loader import ChampionshipLoader
from data.championship.options import ChampionshipCompetitorType

NAME = 'test-championships-http'


@pytest.fixture(params=list(ChampionshipCompetitorType), ids=str)
def championship(request: pytest.FixtureRequest, http: TestClient) -> Iterator[str]:
    """The uniq id of a championship of the parametrised competitor type,
    read from the redirect its creation answers with."""
    response = http.post(
        '/championship-create',
        data={'name': NAME, 'competitor_type': request.param.value},
    )
    assert response.status_code == 201
    location = response.headers['hx-redirect']
    uniq_id = location.split('/championship/')[1].split('/')[0]
    yield uniq_id
    ChampionshipLoader().delete_championship(uniq_id)


def is_a_team_championship(uniq_id: str) -> bool:
    championship = ChampionshipLoader().load_championship(uniq_id)
    return championship.competitor_type == ChampionshipCompetitorType.TEAM


def tab(http: TestClient, uniq_id: str, name: str) -> str:
    response = http.get(f'/championship/{uniq_id}/{name}')
    assert response.status_code == 200
    return response.text


def parse(markup: str) -> AdvancedHTMLParser:
    parser = AdvancedHTMLParser()
    parser.parseStr(markup)
    return parser


def texts(parser: AdvancedHTMLParser, tag_name: str) -> list[str]:
    return [
        ' '.join(element.textContent.split())
        for element in parser.getElementsByTagName(tag_name)
    ]


@pytest.mark.unit
def test_a_new_championship_opens_on_its_configuration(
    http: TestClient, championship: str
):
    response = http.get(f'/championship/{championship}/configuration')
    assert response.status_code == 200
    assert NAME in response.text
    for name in ('competitors', 'sources', 'results'):
        assert f'data-testid="nav-{name}-tab"' in response.text


@pytest.mark.unit
def test_the_competitors_are_the_teams_or_the_players(
    http: TestClient, championship: str
):
    parser = parse(tab(http, championship, 'competitors'))
    assert parser.getElementById('championship-competitors-table') is not None
    merge = parser.getElementById('championship-merge-competitors')
    assert merge is not None
    assert merge.hasAttribute('disabled')
    headers = texts(parser, 'th')
    if is_a_team_championship(championship):
        assert 'Merge selected teams' in merge.textContent
        assert 'Team' in headers
        assert 'Cat.' not in headers
        assert 'Gen.' not in headers
    else:
        assert 'Merge selected players' in merge.textContent
        assert 'Player' in headers
        assert 'Cat.' in headers
        assert 'Gen.' in headers


@pytest.mark.unit
def test_the_configuration_offers_the_sections_of_its_competitor_type(
    http: TestClient, championship: str
):
    markup = tab(http, championship, 'configuration')
    team = is_a_team_championship(championship)
    assert ('Team score basis' in markup) is team
    assert ('Ranking categories' in markup) is not team


@pytest.mark.unit
def test_the_results_start_with_the_general_ranking_alone(
    http: TestClient, championship: str
):
    markup = tab(http, championship, 'results')
    selector = re.search(
        r'id="championship-ranking-selector".*?</select>', markup, re.DOTALL
    )
    assert selector is not None
    assert re.findall(r'<option value="([^"]+)"', selector.group()) == ['overall']
    assert 'General ranking' in texts(parse(markup), 'h3')


@pytest.mark.unit
def test_without_a_compatible_tournament_no_source_is_offered(
    http: TestClient, championship: str
):
    response = http.get(f'/championship/{championship}/source-modal')
    assert response.status_code == 200
    assert 'There are no other compatible tournaments available.' in response.text
