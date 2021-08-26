import pytest

pytestmark = pytest.mark.asyncio


async def test_yaml_loading(avrae, dhttp):
    yaml_string = """key1:\n nested_key1: 06-08-2012\n nested_key2: value2\n nested_key3: value3\nthing1: """ \
                  """one\nthing2: two\nthing3:\n - 1\n - 2\n - 3 """

    dhttp.clear()
    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''loaded['thing1']\n</drac2>''')
    await dhttp.receive_message(r".*: one", regex=True)

    await dhttp.drain()
    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''loaded['thing3']\n</drac2>''')
    await dhttp.receive_message(r'.*: \[1, 2, 3\]', regex=True)


async def yaml_test_types(avrae, dhttp):
    yaml_string = """key1:\n nested_key1: 06-08-2012\n nested_key2: value2\n nested_key3: value3\nthing1: """ \
                  """one\nthing2: two\nthing3:\n - 1\n - 2\n - 3 """

    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded)\n</drac2>''')
    await dhttp.receive_message(r'.*: SafeDict', regex=True)

    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded['thing3'])\n</drac2>''')
    await dhttp.receive_message(r'.*: SafeList', regex=True)

    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded['key1'])\n</drac2>''')
    await dhttp.receive_message(r'.*: SafeDict', regex=True)

    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded['thing3'][1])\n</drac2>''')
    await dhttp.receive_message(r'.*: int', regex=True)

# Will add these once I understand the errors better.
# async def yaml_test_errors(avrae, dhttp):
#     yaml_string = """key1:\n nested_key1: 06-08-2012\n nested_key2: value2\n nested_key3: value3\nthing1: """ \
#                   """one\nthing2: two\nthing3:\n - 1\n - 2\n - 3 """
#     avrae.message('!test {{load_yaml(4)}}')
#     await dhttp.receive_message("Error evaluating expression: 'int' object has no attribute 'read'", regex=False)
#
#     avrae.message('!test {{load_yaml("key1: key2: key3")}}')
#     await dhttp.receive_message('Error evaluating expression: maximum recursion depth exceeded in comparison',
#                                 regex=False)


async def yaml_test_dumping(avrae, dhttp):
    yaml_string = """key1:\n nested_key1: 06-08-2012\n nested_key2: value2\n nested_key3: value3\nthing1: """ \
                  """one\nthing2: two\nthing3:\n - 1\n - 2\n - 3 """
    avrae.message("""!test <drac2>\ndata = {"name": "Dice", "age": "old", "languages": 3, "drinks": ["beer","""
                  """ "wine", "apple juice"]}\nreturn dump_yaml(data)\n</drac2>""")
    await dhttp.recieve_message("age: old\ndrinks:\n - beer\n - wine\n - apple juice\nlanguages: 3\nname: Dice",
                                regex=False)
