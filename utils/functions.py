'''
Created on Oct 29, 2016

@author: andrew
'''
import errno
import os
import re

from fuzzywuzzy import process, fuzz

from cogs5e.funcs.dice import roll


def print_table(table):
    tableStr = ''
    col_width = [max(len(x) for x in col) for col in zip(*table)]
    for line in table:
        tableStr += "| " + " | ".join("{:{}}".format(x, col_width[i])
                                for i, x in enumerate(line)) + " |"
        tableStr += '\n'
    return tableStr

def discord_trim(str):
    result = []
    trimLen = 0
    lastLen = 0
    while trimLen <= len(str):
        trimLen += 1999
        result.append(str[lastLen:trimLen])
        lastLen += 1999
    return result

def embed_trim(str):
    result = []
    trimLen = 0
    lastLen = 0
    while trimLen <= len(str):
        trimLen += 1023
        result.append(str[lastLen:trimLen])
        lastLen += 1023
    return result

def list_get(index, default, l):
    try:
        a = l[index]
    except IndexError:
        a = default
    return a

def make_sure_path_exists(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise
        
def get_positivity(string):
    if isinstance(string, bool): # oi!
        return string
    lowered = string.lower()
    if lowered in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
        return True
    elif lowered in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
        return False
    else:
        return None
    
def fuzzy_search(list_to_search:list, key, value):
    """Fuzzy searches a list for a dict with a key "key" of value "value" """
    try:
        result = next(a for a in list_to_search if value.lower() == a.get(key, '').lower())
    except StopIteration:
        try:
            result = next(a for a in list_to_search if value.lower() in a.get(key, '').lower())
        except StopIteration:
            return None
    return result 

def fuzzywuzzy_search(list_to_search:list, key, value):
    """Fuzzy searches a list for a dict with a key "key" of value "value" """
    names = [d[key] for d in list_to_search]
    result = process.extractOne(value, names, score_cutoff=5)
    if result is None: return None
    else: return next(a for a in list_to_search if result[0] == a.get(key, ''))
    
def fuzzywuzzy_search_all_old(list_to_search:list, key, value):
    """Fuzzy searches a list for a dict with all keys "key" of value "value" """
    names = [d[key] for d in list_to_search]
    result = process.extract(value, names, scorer=fuzz.ratio)
    if len(result) is 0: return None
    else: return result
    
def fuzzywuzzy_search_all(list_to_search:list, key, value):
    """Fuzzy searches a list for a dict with all keys "key" of value "value" """
    try:
        result = next(a for a in list_to_search if value.lower() == a.get(key, '').lower())
    except StopIteration:
        try:
            result = next(a for a in list_to_search if value.lower() in a.get(key, '').lower())
        except StopIteration:
            names = [d[key] for d in list_to_search]
            result = process.extract(value, names, scorer=fuzz.ratio)
            if len(result) is 0: return None
            else: return result
    return [(result[key], 99)]

def parse_args(args):
    out = {}
    index = 0
    for a in args:
        if a == '-b' or a == '-d':
            if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, None, args)
            else: out[a.replace('-', '')] += ' + ' + list_get(index + 1, None, args)
        elif a.startswith('-'):
            nextArg = list_get(index + 1, None, args)
            if nextArg is None or nextArg.startswith('-'): nextArg = True
            out[a.replace('-', '')] = nextArg
        else:
            out[a] = "True"
        index += 1
    return out

def parse_args_2(args):
    out = {}
    index = 0
    cFlag = False
    for a in args:
        if cFlag:
            cFlag = False
            continue
        if a == '-b' or a == '-d' or a == '-c':
            if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, '0', args)
            else: out[a.replace('-', '')] += ' + ' + list_get(index + 1, '0', args)
        elif re.match(r'-d\d+', a) or a.strip('-') in ('resist', 'immune', 'vuln'):
            if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, '0', args)
            else: out[a.replace('-', '')] += '|' + list_get(index + 1, '0', args)
        elif a in ('-phrase'):
            if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = list_get(index + 1, '0', args)
            else: out[a.replace('-', '')] += '\n' + list_get(index + 1, '0', args)
        elif a.startswith('-'):
            if list_get(index + 1, 'MISSING_ARGUMENT', args).startswith('-'):
                out[a.replace('-', '')] = 'True'
                index += 1
                continue
            else:
                out[a.replace('-', '')] = list_get(index + 1, 'MISSING_ARGUMENT', args)
        else:
            out[a] = 'True'
            index += 1
            continue
        index += 2
        cFlag = True
    return out

def parse_args_3(args):
    out = {}
    index = 0
    for a in args:
        if a.startswith('-'):
            if out.get(a.replace('-', '')) is None: out[a.replace('-', '')] = [list_get(index + 1, '0', args)]
            else: out[a.replace('-', '')].append(list_get(index + 1, 'MISSING_ARGUMENT', args))
        else:
            if out.get(a) is None: out[a] = ["True"]
            else: out[a].append("True")
        index += 1
    return out

def a_or_an(string):
    if re.match('[AEIOUaeiou].*', string):
        return 'an {0}'.format(string)
    return 'a {0}'.format(string)

def camel_to_title(string):
    return re.sub(r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', string).title()

def text_to_numbers(string):
    numbers = {'one': '1',
               'two': '2',
               'three': '3',
               'four': '4',
               'five': '5',
               'six': '6',
               'seven': '7',
               'eight': '8',
               'nine': '9',
               'ten': '10',
               'once': '1',
               'twice': '2',
               'thrice': '3'}
    for t, i in numbers.items():
        string = string.replace(t, i)
    return string

def parse_cvars(cstr, character):
    """Parses cvars.
    cstr - The string to parse.
    character - the Character dict of a character."""
    ops = r"([-+*/().<>=])"
    cvars = character.get('cvars', {})
    stat_vars = character.get('stat_cvars', {})
    for var in re.finditer(r'{([^{}]+)}', cstr):
        raw = var.group(0)
        varstr = var.group(1)
        out = ""
        for substr in re.split(ops, varstr):
            temp = substr.strip()
            temp = str(cvars.get(temp, temp))
        for substr in re.split(ops, temp):
            temp = substr.strip()
            out += str(stat_vars.get(temp, temp)) + " "
        cstr = cstr.replace(raw, str(roll(out).total), 1)
    for var in re.finditer(r'<([^<>]+)>', cstr):
        raw = var.group(0)
        out = var.group(1)
        out = str(cvars.get(out, out))
        out = str(stat_vars.get(out, out))
        cstr = cstr.replace(raw, out, 1)
    return cstr
    