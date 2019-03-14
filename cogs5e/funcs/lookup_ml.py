import itertools
import logging

import numpy as np
import tensorflow as tf
from fuzzywuzzy import fuzz, process

from cogs5e.funcs.lookupFuncs import c

MODEL_NAME = "spells"
ALLOWED_CHARACTERS = "abcdefghijklmnopqrstuvwxyz '"
INPUT_LENGTH = 16

log = logging.getLogger(__name__)


def build_spell_model():
    model = tf.keras.models.load_model(f'./res/spell-nn/{MODEL_NAME}.h5')
    return model


spell_model = build_spell_model()


def clean(query):
    filtered = query.lower()
    filtered = ''.join(c for c in filtered if c in ALLOWED_CHARACTERS)
    return filtered[:INPUT_LENGTH].strip()


def tokenize(query, magic_string, use_index=False):
    num_chars = len(magic_string)
    if not use_index:
        tokenized = [0.] * INPUT_LENGTH
        for i, char in enumerate(query):
            tokenized[i] = (magic_string.index(char) + 1) / num_chars
    else:
        tokenized = [0] * INPUT_LENGTH
        for i, char in enumerate(query):
            tokenized[i] = magic_string.index(char) + 1
    return tokenized


def get_spell_model_predictions(query, num_matches=5):
    log.debug(f"Query: {query}")
    query = clean(query)
    query = tokenize(query, ALLOWED_CHARACTERS, True)  # Set to False if not using embedding
    query = np.expand_dims(query, 0)

    prediction = spell_model.predict(query)
    prediction = prediction[0]

    indexed = list(enumerate(prediction))
    weighted = sorted(indexed, key=lambda e: e[1], reverse=True)

    log.debug('\n'.join([f"{c.spells[r[0]].name}: {r[1]:.2f}" for r in weighted[:num_matches]]))

    return [c.spells[r[0]] for r in weighted[:num_matches]], [r[1] for r in weighted[:num_matches]]


def weave(*iterables):
    return [a for b in itertools.zip_longest(*iterables) for a in b if a is not None]


async def ml_spell_search(list_to_search: list, value, key, cutoff=5, return_key=False):
    """Fuzzy searches a list for an object
    result can be either an object or list of objects
    :param list_to_search: The list to search.
    :param value: The value to search for.
    :param key: A function defining what to search for.
    :param cutoff: The scorer cutoff value for fuzzy searching.
    :param return_key: Whether to return the key of the object that matched or the object itself.
    :returns: A two-tuple (result, strict) or None"""
    # full match, return result
    result = next((a for a in list_to_search if value.lower() == key(a).lower()), None)
    if result is None:
        partial_matches = [a for a in list_to_search if value.lower() in key(a).lower()]
        if len(partial_matches) > 1 or not partial_matches:
            names = [key(d) for d in list_to_search]
            fuzzy_map = {key(d): d for d in list_to_search}
            fuzzy_results = [r for r in process.extract(value, names, scorer=fuzz.ratio) if r[1] >= cutoff]
            fuzzy_sum = sum(r[1] for r in fuzzy_results)
            fuzzy_matches_and_confidences = [(fuzzy_map[r[0]], r[1] / fuzzy_sum) for r in fuzzy_results]
            # hardcoded to return only non-homebrew spells
            net_matches, net_confidences = get_spell_model_predictions(value, 10)

            # display the results in order of confidence
            weighted_results = []
            weighted_results.extend((match, confidence) for match, confidence in zip(net_matches, net_confidences))
            weighted_results.extend((match, confidence) for match, confidence in fuzzy_matches_and_confidences)
            weighted_results.extend((match, len(value) / len(key(match))) for match in partial_matches)
            sorted_weighted = sorted(weighted_results, key=lambda e: e[1], reverse=True)
            log.debug('\n'.join(f"{key(r[0])}: {r[1]:.2f}" for r in sorted_weighted))

            # build results list, unique
            results = []
            for r in sorted_weighted:
                if r[0] not in results:
                    results.append(r[0])
        else:
            results = partial_matches
        if return_key:
            return [key(r) for r in results], False
        else:
            return results, False
    if return_key:
        return key(result), True
    else:
        return result, True
