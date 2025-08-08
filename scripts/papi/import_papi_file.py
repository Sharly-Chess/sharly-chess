import json

from data.input_output.dict_reader import dict_to_dataclass
from plugins.ffe.papi_converter import PapiData

with open('papi/domloup-fide-37-a.json', 'r', encoding='utf-8') as file:
    dict_example = json.load(file)

papi_data = dict_to_dataclass(PapiData, dict_example)
papi_round = papi_data.players[0].rounds[1]
print(papi_round)
