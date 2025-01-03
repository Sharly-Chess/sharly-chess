import toml
from validate_pyproject import api, errors

pyproject_as_dict = toml.load('pyproject.toml')
print(pyproject_as_dict)
validator = api.Validator()

try:
    validator(pyproject_as_dict)
except errors.ValidationError as ex:
    print(f'Invalid Document: {ex.message}')