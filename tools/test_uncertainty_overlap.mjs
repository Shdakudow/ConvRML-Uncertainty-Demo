/* Known overlap sets in the exact browser algorithm, without canvas rendering. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../uncertainty-agreement.js', import.meta.url), 'utf8');
const context = {window: {}, document: {currentScript: {src: 'http://localhost/uncertainty-agreement.js'}}, URL, Float32Array, Uint8Array, Number, Math, Array, Error};
vm.createContext(context); vm.runInContext(source, context);
const {differences} = context.window.UncertaintyAgreement;
function map(values, excluded = []) {
  const buffer = new ArrayBuffer(values.length*4), view = new DataView(buffer);
  values.forEach((value,index) => view.setFloat32(index*4,value,true));
  const crossing = new Uint8Array(Math.ceil(values.length/8));
  for (const p of excluded) crossing[p>>3] |= 1 << (7-(p&7));
  return {width: values.length, height: 1, values: view, crossing};
}
const a = Array.from({length: 100},(_,index)=>index);
let result = differences(map(a),map(a.map(value=>5*value+2)));
assert.equal(result.top10.top10_iou,1); assert.equal(result.top10.top10_intersection,10);
assert.equal([...result.overlapClasses].filter(v=>v===3).length,10);
result = differences(map(a),map([...a].reverse())); assert.equal(result.top10.top10_iou,0);
const shifted = a.slice(-5).concat(a.slice(0,-5));
result = differences(map(a),map(shifted));
assert.equal(result.top10.top10_intersection,5); assert.equal(result.top10.top10_union,15); assert.equal(result.top10.top10_iou,1/3);
const tied = a.slice(0,80).concat(Array(20).fill(100));
assert.equal(differences(map(tied),map(tied)).top10.top10_qutcc_count,20);
assert.equal(differences(map(a),map(Array(100).fill(1))).top10.top10_iou,null);
result = differences(map(a,[99]),map(a)); assert.equal(result.top10.top10_valid_pixels,99); assert.equal(result.overlapClasses[99],255);
const invalid = [...a];invalid[10]=NaN;
assert.equal(differences(map(invalid),map(a)).top10.top10_valid_pixels,99);
console.log('PASS: browser overlap sets, partial intersection/union, shared crossings, nonfinite values, cutoff ties, constant-map handling.');
