import tomllib
from validate_pyproject import api, errors

with open('pyproject.toml', 'rb') as f:
    pyproject_as_dict = tomllib.load(f)
print(pyproject_as_dict)
validator = api.Validator()

try:
    validator(pyproject_as_dict)
except errors.ValidationError as ex:
    print(f'Invalid Document: {ex.message}')
