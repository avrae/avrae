'''
Created on Oct 29, 2016

@author: andrew
'''
import os
import errno


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
    lowered = string.lower()
    if lowered in ('yes', 'y', 'true', 't', '1', 'enable', 'on'):
        return True
    elif lowered in ('no', 'n', 'false', 'f', '0', 'disable', 'off'):
        return False
    else:
        return None