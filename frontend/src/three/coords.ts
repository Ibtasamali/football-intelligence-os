// Event coordinates are metres on a 105 × 68 pitch (home attacks towards x = 105).
// World: x → X (−52.5..52.5), y → Z (−34..34), Y is up.
export const L = 105;
export const W = 68;
export const toWorld = (x: number, y: number, h = 0): [number, number, number] => [x - L / 2, h, y - W / 2];
