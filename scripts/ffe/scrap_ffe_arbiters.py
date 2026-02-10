from typing import Counter

from plugins.ffe.ffe_session import FFEArbitersLoader
from plugins.ffe.utils import FFEArbiterTitle


print('Loading arbiters from the FFE website...')
counter = Counter[FFEArbiterTitle]()
for ffe_licence_number, ffe_arbiter_title in (
    FFEArbitersLoader().load_ffe_arbiter_titles_by_ffe_licence_number().items()
):
    counter[ffe_arbiter_title] += 1

for ffe_arbiter_title in FFEArbiterTitle:
    if counter[ffe_arbiter_title]:
        print(f'{ffe_arbiter_title}: {counter[ffe_arbiter_title]}')
