// Strict independent assertions for the explicit grouped-member discriminator.
// No proof is produced here: callers supply actual server response JSON.
import assert from 'node:assert/strict';
import {assertEffectiveBounds} from './bounds_assertions.mjs';
export const GROUPING_POLICY='PINNED_V031_SE3_FIRST_REPRESENTATIVE_V1';
const finite=x=>assert.equal(Number.isFinite(x),true);
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);
const wrapped=x=>Math.atan2(Math.sin(x),Math.cos(x));
export function assertGroupProof(response,{requireCurrentMembersInBounds=true}={}){
 const p=response.operator_prior_resolution,c=response.current_vs_prior,b=assertEffectiveBounds(p);
 assert.equal(p.grouping_policy,GROUPING_POLICY);assert.equal(p.matching_hypothesis_count,1);
 const n=p.matching_candidate_count;assert.ok(Number.isInteger(n)&&n>=1&&n<=p.eligible_candidate_count);assert.equal(p.matching_retained_candidate_count,n);
 assert.ok(Number.isInteger(p.verified_duplicate_count)&&p.verified_duplicate_count>=n-1&&p.verified_duplicate_count<=p.eligible_candidate_count-1);
 const indices=p.matching_member_indices,geometry=p.matching_member_geometry;assert.equal(indices.length,n);assert.equal(geometry.length,n);assert.equal(indices[0],p.candidate_index);
 indices.forEach((index,i)=>{assert.ok(Number.isInteger(index)&&index>=0&&index<p.retained_candidate_count&&(i===0||indices[i-1]<index));const g=geometry[i];assert.equal(g.candidate_index,index);for(const key of ['z_m','roll_rad','pitch_rad','z_delta_m','roll_delta_rad','pitch_delta_rad'])finite(g[key]);close(g.z_delta_m,g.z_m-geometry[0].z_m);close(g.roll_delta_rad,wrapped(g.roll_rad-geometry[0].roll_rad));close(g.pitch_delta_rad,wrapped(g.pitch_rad-geometry[0].pitch_rad));});
 assert.ok(c&&Array.isArray(c.member_checks));assert.equal(c.member_checks.length,n);assert.match(c.pose_stamp_ns,/^[1-9][0-9]*$/);finite(c.pose_age_s);assert.ok(c.pose_age_s>=0&&c.pose_age_s<=1);
 c.member_checks.forEach((m,i)=>{assert.equal(m.candidate_index,indices[i]);finite(m.xy_distance_m);finite(m.absolute_wrapped_yaw_rad);assert.ok(m.xy_distance_m>=0&&m.absolute_wrapped_yaw_rad>=0&&m.absolute_wrapped_yaw_rad<=Math.PI);assert.equal(m.within_prior_bounds,m.xy_distance_m<=b.xy_m&&m.absolute_wrapped_yaw_rad<=b.yaw_rad);});
 assert.equal(c.all_members_within_prior_bounds,c.member_checks.every(m=>m.within_prior_bounds));if(requireCurrentMembersInBounds)assert.equal(c.all_members_within_prior_bounds,true);
 assert.equal(c.within_prior_bounds,c.member_checks[0].within_prior_bounds);close(c.xy_distance_m,c.member_checks[0].xy_distance_m);close(Math.abs(c.yaw_delta_rad),c.member_checks[0].absolute_wrapped_yaw_rad);
 return p;
}
export function assertHandoffMembers(handoff,response){
 const p=response.operator_prior_resolution,b=assertEffectiveBounds(p),m=handoff.operator_prior_current_members;assert.ok(m);assert.match(m.pose_stamp_ns,/^[1-9][0-9]*$/);assert.equal(m.member_checks.length,p.matching_member_indices.length);
 m.member_checks.forEach((v,i)=>{assert.equal(v.candidate_index,p.matching_member_indices[i]);assert.equal(v.within_prior_bounds,true);assert.ok(v.xy_distance_m>=0&&v.xy_distance_m<=b.xy_m);assert.ok(v.absolute_wrapped_yaw_rad>=0&&v.absolute_wrapped_yaw_rad<=b.yaw_rad);});
}
