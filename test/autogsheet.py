import pygsheets


def main():
    gc = pygsheets.authorize(service_file='../avrae-0b82f09d7ab3.json')

if __name__ == '__main__':
    main()