import re
import timeit


def find_inline_exprs(content, context_before=5, context_after=2, max_context_len=128):
    """Returns an iterator of tuples (expr, context_before, context_after)."""
    content_len = len(content)

    # all content indexes
    idxs = []
    for start, expr_start, expr_end, end in _find_roll_expr_indices(content):
        before_idx = max(0, start - max_context_len)
        before_fragment = content[before_idx:start]
        before_bits = before_fragment.rsplit(maxsplit=context_before)
        if len(before_bits) > context_before:
            before_idx += len(before_bits[0])

        after_idx = min(content_len, end + max_context_len)
        after_fragment = content[end:after_idx]
        after_bits = after_fragment.split(maxsplit=context_after)
        if len(after_bits) > context_after:
            after_idx -= len(after_bits[-1])

        idxs.append(((before_idx, start), (expr_start, expr_end), (end, after_idx)))

    # start boundaries
    for i, ((before_idx, start), (expr_start, expr_end), (end, after_idx)) in enumerate(idxs[1:], start=1):
        clamped_before_idx = max(before_idx, idxs[i - 1][2][0])
        idxs[i] = (clamped_before_idx, start), (expr_start, expr_end), (end, after_idx)

    # end boundaries
    for i, ((before_idx, start), (expr_start, expr_end), (end, after_idx)) in enumerate(idxs[:-1]):
        clamped_after_idx = min(after_idx, idxs[i + 1][0][0])
        idxs[i] = (before_idx, start), (expr_start, expr_end), (end, clamped_after_idx)

    # turn into the exprs
    for ((before_idx, start), (expr_start, expr_end), (end, after_idx)) in idxs:
        context_before = content[before_idx:start].lstrip()
        expr = content[expr_start:expr_end].strip()
        context_after = content[end:after_idx].rstrip()

        # ellipsis handling
        if before_idx > 0:
            context_before = f"...{context_before}"
        if after_idx < content_len:
            context_after = f"{context_after}..."

        yield expr, context_before, context_after


def _find_roll_expr_indices(content):
    """
    Returns an iterator of tuples (start, expr_start, expr_end, end) representing the indices of the roll exprs found
    (outside and inside the braces).
    """
    content_len = len(content)
    end = 0
    while (start := content.find('[[', end)) != -1:
        end = content.find(']]', start)
        if end == -1:
            break
        if end + 2 < content_len and content[end + 2] == ']':
            end += 1
        yield start, start + 2, end, end + 2


_EXPR_RE = re.compile(r'\[\[(.+?]?)]]')


def find_inline_exprs_regex(content, context_before=5, context_after=2, max_context_len=128):
    # create list alternating (before, expr; text, expr; ...; text, expr; after)
    segments = _EXPR_RE.split(content)

    # want (before, expr, after; ...; before, expr, after)
    # so split up each pair of (text, expr) by trimming the text into (last_after, before, expr)
    # with priority on before
    trimmed_segments = []
    for text, expr in zip(a := iter(segments), a):  # fun way to take pairs from a list!
        text_len = len(text)

        # before is always text[before_idx:len(text)]
        before_idx = 0
        before_bits = text.rsplit(maxsplit=context_before)
        if len(before_bits) > context_before:
            before_idx += len(before_bits[0])
        before_idx = max(before_idx, text_len - max_context_len)
        before = text[before_idx:text_len]

        # last_after is always text[0:last_after_end_idx]
        last_after_end_idx = text_len
        after_bits = text.split(maxsplit=context_after)
        if len(after_bits) > context_after:
            last_after_end_idx -= len(after_bits[-1])
        last_after_end_idx = min(last_after_end_idx, before_idx)
        last_after = text[0:last_after_end_idx]

        trimmed_segments.extend((last_after, before, expr))

    # now we have (junk, before, expr; after, before, expr; ...; after, before, expr)
    # discard the first junk
    discarded_before = trimmed_segments.pop(0)
    # and clean up the last after
    discarded_after = False
    last_after = segments[-1]
    last_after_end_idx = len(last_after)
    after_bits = last_after.split(maxsplit=context_after)
    if len(after_bits) > context_after:
        last_after_end_idx -= len(after_bits[-1])
        discarded_after = True
    trimmed_segments.append(last_after[0:last_after_end_idx])
    # we also use whether or not the chopped-off bits at the very start and end exist for ellipses

    # now we have (before, expr, after; ...)
    # do ellipses and yield triples (expr, context_before, context_after)
    num_triples = len(trimmed_segments) // 3
    for idx, (before, expr, after) in enumerate(zip(a := iter(trimmed_segments), a, a)):
        context_before = before.lstrip()
        context_after = after.rstrip()

        if idx or discarded_before:  # not the first or something was discarded before first
            context_before = f"...{context_before}"

        if idx + 1 < num_triples or discarded_after:  # not the last or something was discarded after last
            context_after = f"{context_after}..."

        yield expr.strip(), context_before, context_after


def _find_roll_expr_indices_regex(content):
    for match in _EXPR_RE.finditer(content):
        yield match.start(), match.start(1), match.end(1), match.end()


test_strs = {
    "small1": "Do [[1d2]] believe [[1d4]] miracles? [[1d8]] does, so does [[1d12]]",
    "small2": "I attack with my axe [[1d20+5]], then rapier [[1d20+3]].",
    "long1": """In academic writing, readers expect each paragraph to have a sentence or two that captures its main 
    point. They’re often called “topic sentences,” though many writing instructors prefer to call them “key 
    sentences.” There are at least two downsides of the phrase “topic sentence.” [[1d20]], it makes it seem like the 
    paramount job of that sentence is simply to announce the topic of the paragraph. Second, it makes it seem like 
    the topic sentence must always be a single grammatical sentence. Calling it a “key sentence” reminds us that it 
    expresses the central idea of the [[2d20 + 30 [academia psychic] ]]. And sometimes a question or a two-sentence 
    construction functions as the key.""",
    "long2": """There once was a ship that put to sea 
    The name of the ship was the Billy of Tea
    The winds blew up, her bow dipped down
    Oh blow, my bully boys, blow [[1d20+5]]
    Soon may the Wellerman come
    To bring us sugar and tea and rum
    One day, when the tonguing is done
    We'll take our leave and go [[1d8 + 5 [magical wellerman] ]]
    She'd not been two weeks from shore
    When down on her a right whale bore
    The captain called all hands and swore
    He'd take that whale in tow (huh)""",
    "long3": "[[1d20]] " * 1000,
    "dtypes": "[[1d20[test]]]",
    "dtypeslong": "foobar [[1d20[test]]] foobar " * 50,
    "dtypeslonger": "foobar [[1d20[test]]] foobar " * 500
}


def create_output(timeit_result):
    repetitions, total_time = timeit_result
    avg_time = total_time / repetitions
    avg_time_ns = avg_time * 1000 * 1000 * 1000
    return f"avg: {avg_time_ns:,.3f}ns ({repetitions:,} runs)"


def consume(iterator):
    for _ in iterator:
        pass


def bench():
    for k, v in test_strs.items():
        assert list(_find_roll_expr_indices(v)) == list(_find_roll_expr_indices_regex(v))
        assert list(find_inline_exprs(v)) == list(find_inline_exprs_regex(v))

        find_indices_nore = timeit.Timer(lambda: consume(_find_roll_expr_indices(v))).autorange()
        find_indices_re = timeit.Timer(lambda: consume(_find_roll_expr_indices_regex(v))).autorange()
        find_expr_nore = timeit.Timer(lambda: consume(find_inline_exprs(v))).autorange()
        find_expr_re = timeit.Timer(lambda: consume(find_inline_exprs_regex(v))).autorange()

        print(f"===== {k} =====")
        print(f"find_indices: nore={create_output(find_indices_nore)}, re={create_output(find_indices_re)}")
        print(f"find_exprs:   nore={create_output(find_expr_nore)}, re={create_output(find_expr_re)}")
        print()


def asdf():
    find_inline_exprs_regex(test_strs['long1'])


def profile():
    for k, v in test_strs.items():
        find_expr_re = timeit.Timer(lambda: consume(find_inline_exprs_regex(v))).autorange()

        print(f"===== {k} =====")
        print(f"find_exprs: {create_output(find_expr_re)}")
        print()


if __name__ == '__main__':
    profile()
