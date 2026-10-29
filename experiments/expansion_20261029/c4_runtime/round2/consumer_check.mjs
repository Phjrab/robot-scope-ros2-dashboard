// Actual pinned C3 consumer, against the actual C1 service snapshot.
import { pathToFileURL } from 'node:url';
import { readFileSync } from 'node:fs';
const [adapter, file] = process.argv.slice(2);
const { adaptC1ScenePacket } = await import(pathToFileURL(adapter));
const wire = JSON.parse(readFileSync(file,'utf8'));
const context = { ...wire.map_binding, frame_id:'odom',source_epoch:'synthetic-1',units:'m' };
const result = adaptC1ScenePacket(wire, context);
console.log(JSON.stringify({status:result.packet ? 'PASS':'FAIL',reason:result.reason}));
process.exitCode = result.packet ? 0 : 2;
