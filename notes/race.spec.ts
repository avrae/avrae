// Note: This spec is not exactly what is used as of build 1234
// but it is representative of what type of data is consumed
// and what schema I plan on changing to in the future
// @ts-ignore
import Feature from './feature.spec.ts';

class Race {
    name: string;
    source: string;
    page: number;
    size: 'S' | 'M';
    speed: {
        walk: number;
        string: number;
    };
    ability: {
        string: number;
    };
    features: Feature[];
    srd: false;
    darkvision: number; // not actually sure why this is here
}