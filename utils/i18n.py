from babel.messages.extract import extract_from_dir

for message in extract_from_dir(
    method_map=[
#        ('venv/.py', 'ignore'),
        ('.py', 'python'),
        ('web/templates/.html', 'html'),
    ],
):
    print(message)