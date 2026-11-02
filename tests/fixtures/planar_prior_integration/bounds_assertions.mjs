// Independent assertion of proof provenance; never produces a server proof.
import assert from 'node:assert/strict';

const shape=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
function assertBounds(bounds){
 assert.ok(shape(bounds));assert.deepEqual(Object.keys(bounds).sort(),['xy_m','yaw_rad']);
 assert.ok(Number.isFinite(bounds.xy_m)&&bounds.xy_m>=.1&&bounds.xy_m<=3);
 assert.ok(Number.isFinite(bounds.yaw_rad)&&bounds.yaw_rad>=Math.PI/180&&bounds.yaw_rad<=Math.PI/2);
}
export function assertEffectiveBounds(proof){
 assert.ok(shape(proof)&&shape(proof.operator_prior));
 const prior=proof.operator_prior,explicit=Object.hasOwn(prior,'bounds');
 if(explicit)assertBounds(prior.bounds);
 const sourcePresent=Object.hasOwn(proof,'bounds_source'),effectivePresent=Object.hasOwn(proof,'effective_bounds');
 assert.equal(sourcePresent,effectivePresent,'both bounds provenance fields are required together');
 if(!sourcePresent){assert.equal(explicit,true,'bounds-free proof cannot use legacy provenance');return prior.bounds;}
 assert.equal(proof.bounds_source,explicit?'operator_prior':'server_policy');assertBounds(proof.effective_bounds);
 assert.deepEqual(proof.effective_bounds,explicit?prior.bounds:{xy_m:.25,yaw_rad:.20});
 return proof.effective_bounds;
}
