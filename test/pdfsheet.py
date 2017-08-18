import json

from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import PSLiteral


def main():
    fn = input("PDF filename: ")
    character = {}
    with open(fn, mode='rb') as f:
        parser = PDFParser(f)
        doc = PDFDocument(parser)
        try:
            fields = resolve1(doc.catalog['AcroForm'])['Fields']
        except:
            raise Exception('This is not a form-fillable character sheet!')
        for i in fields:
            field = resolve1(i)
            name, value = field.get('T'), field.get('V')
            if isinstance(value, PSLiteral):
                value = value.name
            elif value is not None:
                try:
                    value = value.decode('iso-8859-1')
                except:
                    pass

            character[name.decode('iso-8859-1')] = value

        print(character)
    with open('./output/pdfsheet-test.json', mode='w') as f:
        json.dump(character, f, skipkeys=True, sort_keys=True, indent=4)

if __name__ == '__main__':
    main()