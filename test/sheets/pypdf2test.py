import json

from PyPDF2 import PdfFileReader


def main():
    fn = input("PDF filename: ")
    character = {}
    f = PdfFileReader(fn)
    f.read()
    print(f.getFormTextFields())


    with open('./output/pdfsheet-test.json', mode='w') as f:
        json.dump(character, f, skipkeys=True, sort_keys=True, indent=4)

if __name__ == '__main__':
    main()