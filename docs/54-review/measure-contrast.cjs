const fs = require('fs');

const pairs = [
  ['ink on paper', '#132229', '#f7f8f8', 4.5],
  ['slate on paper', '#52626a', '#f7f8f8', 4.5],
  ['petrol on paper', '#0b5d66', '#f7f8f8', 4.5],
  ['white on petrol', '#ffffff', '#0b5d66', 4.5],
  ['focus petrol on paper', '#0b5d66', '#f7f8f8', 3],
  ['decorative divider on white', '#6f8588', '#ffffff', null],
  ['control border on white', '#71878a', '#ffffff', 3],
  ['warning text on warning surface', '#704015', '#fdf3e9', 4.5],
  ['AI note text on AI surface', '#314a4d', '#edf5f4', 4.5],
  ['navigation text on navigation surface', '#405159', '#eef3f3', 4.5],
  ['green score on green surface', '#14553c', '#e3f1ed', 4.5],
  ['orange score on orange surface', '#854312', '#f5eadc', 4.5],
  ['red score on red surface', '#8c3030', '#f7e4e4', 4.5],
  ['link text on white', '#314148', '#ffffff', 4.5],
  ['white text on ink', '#ffffff', '#132229', 4.5],
];

function rgb(hex) { return [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255); }
function linear(value) { return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4; }
function luminance(hex) { const [r, g, b] = rgb(hex).map(linear); return 0.2126 * r + 0.7152 * g + 0.0722 * b; }
function contrast(foreground, background) { const [a, b] = [luminance(foreground), luminance(background)].sort((x, y) => y - x); return (a + 0.05) / (b + 0.05); }

const results = pairs.map(([name, foreground, background, minimum]) => {
  const ratio = contrast(foreground, background);
  return { name, foreground, background, ratio: Number(ratio.toFixed(2)), minimum, passes: minimum === null || ratio >= minimum };
});
fs.writeFileSync('contrast.json', JSON.stringify(results, null, 2));
console.log(JSON.stringify(results, null, 2));
if (results.some((item) => !item.passes)) process.exitCode = 1;
