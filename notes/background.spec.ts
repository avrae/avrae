class Background {
    name: string;
    traits: Trait[];
    proficiencies: BackgroundProficiencies[];
    source: string;  // maybe we should refactor this into a Source model?
    page: number;
    srd: boolean;
}

class Trait {
    name: string;
    text: string; // Markdown-formatted
}

class BackgroundProficiencies {
    skill?: string[];
    language?: string[];
    tool?: string[];
}