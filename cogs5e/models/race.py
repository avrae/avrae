from utils.functions import parse_data_entry


class Race:
    def __init__(self, name: str, source: str, page: int, size: str, speed, asi, entries, srd: bool = False,
                 darkvision: int = 0):
        self.name = name
        self.source = source
        self.page = page
        self.size = size
        self.speed = speed
        self.ability = asi
        self.entries = entries
        self.srd = srd
        self.darkvision = darkvision

    @classmethod
    def from_data(cls, data):
        size = {'T': "Tiny", 'S': "Small", 'M': "Medium", 'L': "Large", 'H': "Huge"}.get(data['size'], 'Unknown')
        return cls(data['name'], data['source'], data['page'], size, data['speed'], data.get('ability', {}),
                   data['entries'], data['srd'], data.get('darkvision', 0))

    def get_speed_str(self):
        if isinstance(self.speed, int):
            return f"{self.speed} ft."
        elif isinstance(self.speed, dict):
            return ', '.join(f"{k} {v} ft." for k, v in self.speed.items())
        return str(self.speed)

    def get_speed_int(self):
        if isinstance(self.speed, int):
            return self.speed
        elif isinstance(self.speed, dict):
            return self.speed.get('walk', '30')
        return None

    def get_asi_str(self):
        ability = []
        for k, v in self.ability.items():
            if not k == 'choose':
                ability.append(f"{k} {v}")
            else:
                ability.append(f"Choose {v[0]['count']} from {', '.join(v[0]['from'])} {v[0].get('amount', 1)}")
        return ', '.join(ability)

    def get_traits(self):
        traits = []
        for entry in self.entries:
            if isinstance(entry, dict) and 'name' in entry:
                temp = {'name': entry['name'],
                        'text': parse_data_entry(entry['entries'])}
                traits.append(temp)
        return traits
