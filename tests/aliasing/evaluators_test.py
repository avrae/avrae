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
    
    await dhttp.drain()
    avrae.message(f'''!test <drac2>\nyaml_string = 4\nreturn load_yaml(yaml_string)\n</drac2>''')
    await dhttp.receive_message(r'.*: 4')


async def yaml_test_types(avrae, dhttp):
    yaml_string = """key1:\n nested_key1: 06-08-2012\n nested_key2: value2\n nested_key3: value3\nthing1: """ \
                  """one\nthing2: two\nthing3:\n - 1\n - 2\n - 3 """

    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded)\n</drac2>''')
    await dhttp.receive_message(r'.*: SafeDict', regex=True)

    await dhttp.drain()
    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded['thing3'])\n</drac2>''')
    await dhttp.receive_message(r'.*: SafeList', regex=True)

    await dhttp.drain()
    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded['key1'])\n</drac2>''')
    await dhttp.receive_message(r'.*: SafeDict', regex=True)

    await dhttp.drain()
    avrae.message(f'''!test <drac2>\nyaml_string = """{yaml_string}"""\nloaded = load_yaml(yaml_string)\nreturn '''
                  '''typeof(loaded['thing3'][1])\n</drac2>''')
    await dhttp.receive_message(r'.*: int', regex=True)

    await dhttp.drain()
    avrae.message('!test {{typeof(load_yaml("key: /X17unp5WZmZgAAAOfn515eXvPz7Y6O")["key"])}}')
    await dhttp.receive_message(r'.*: str', regex=True)

    await dhttp.drain()
    avrae.message('!test {{typeof(load_yaml("key: 3.1415")["key"])}}')
    await dhttp.receive_message(r'.*: float', regex=True)
    
    await dhttp.drain()
    avrae.message('!test {{typeof(load_yaml("key: y")["key"])}}')
    await dhttp.receive_message(r'.*: bool', regex=True)
    
    await dhttp.drain()
    avrae.message('!test {{typeof(load_yaml("key: 2001-02-03")["key"])}}')
    await dhttp.receive_message(r'.*: str', regex=True)

    await dhttp.drain()
    avrae.message('!test {{typeof(load_yaml("key: ~")["key"])}}')
    await dhttp.receive_message(r'.*: NoneType', regex=True)


async def yaml_test_dumping(avrae, dhttp):
    avrae.message("""!test <drac2>\ndata = {"name": "Dice", "age": "old", "languages": 3, "drinks": ["beer","""
                  """ "wine", "apple juice"]}\nreturn dump_yaml(data)\n</drac2>""")
    await dhttp.recieve_message("age: old\ndrinks:\n - beer\n - wine\n - apple juice\nlanguages: 3\nname: Dice",
                                regex=False)
