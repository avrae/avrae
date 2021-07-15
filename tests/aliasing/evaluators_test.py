from aliasing.evaluators import ScriptingEvaluator


def test_yaml_loading_and_dumping():
    yaml_string = """
    key1:
       nested_key1: 06-08-2012
       nested_key2: value2
       nested_key3: value3
    thing1: one
    thing2: two
    thing3:
     - 1
     - 2
     - 3
    """
    # TODO write more and better tests
    # setup since importing is hard, I know it's... something but it works?

    class ChannelOrAuthorThing:
        def __init__(self):
            self.id = 123
            self.name = 'Dice'
            self.discriminator = '6153'
            self.display_name = 'Dice{They/Them}'
            self.topic = ''

        def __str__(self):
            return '123'

    class ContextWithStuff:
        def __init__(self):
            self.guild = None
            self.channel = ChannelOrAuthorThing()
            self.author = ChannelOrAuthorThing()
            self.prefix = '!'
            self.invoked_with = 'Me'

    e = ScriptingEvaluator(ContextWithStuff())
    _safe_dict = e._dict
    _safe_list = e._list
    _safe_str = e._str

    # ==== Loading ====
    loaded_yaml = e.eval(f'''load_yaml("""{yaml_string}""")''')

    # First we check if it's the right type
    assert isinstance(loaded_yaml, _safe_dict)

    # ==== Dumping ====
    dumped_again = e.eval(f'''dump_yaml("""{loaded_yaml}""")''')
    assert isinstance(dumped_again, _safe_str)

    reloaded = e.eval(f"""load_yaml('''{dumped_again}''')""")
    assert isinstance(reloaded, _safe_dict)

    redumped = e.eval(f'''dump_yaml("""{reloaded}""")''')
    assert isinstance(redumped, _safe_str)
