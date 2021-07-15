from aliasing.evaluators import ScriptingEvaluator
import re


def test_yaml_loading_and_dumping():
    yaml_string = """
    key1:
     - nested_key1: 06-08-2012
     - nested_key2: value2
     - nested_key3: value3
    thing1: one
    thing2: two
    thing3:
     - 1
     - 2
     - 3
    """
    # TODO write more and better tests
    # setup since importing is hard
    evaluator = ScriptingEvaluator(None)

    # ==== Loading ====
    # First we check if it's the right type
    results = evaluator.eval(f"load_yaml({yaml_string})")
    assert re.match(r"""{"\w+\d": .*, "\w+\d": .*}""", results)

    # ==== Dumping ====
    results = evaluator.eval("""d = {'key1': 'value1'}
    dump_yaml(d)
    """)
    assert re.match('''["|']key1 ?["|']: ['|"]value1 ?['|"]''', results)
