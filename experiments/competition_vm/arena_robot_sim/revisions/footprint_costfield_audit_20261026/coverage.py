"""Finite synthetic discretization counterexamples; no native execution."""
import json
import math
from pathlib import Path
from audit import H, RI, RC, PADDED, corners, grid_cell, emitted_cost, inflation_cost, gate


def evaluate():
    threshold=inflation_cost(RC)
    rows=[]
    for yaw_step in range(64):
        yaw=yaw_step*2*math.pi/64
        for dx in [0,.25,.5,.95]:
            for dy in [0,.25,.5,.95]:
                pose=[1+dx*H,1+dy*H,yaw]
                center=grid_cell(pose[:2],[0,0],H)
                for corner in corners(pose):
                    vertex=grid_cell(corner,[0,0],H)
                    distance=H*math.dist(center,vertex)
                    rows.append((distance,pose,center,vertex))
    worst=max(rows,key=lambda x:x[0])
    smac=[]
    headings=[0, math.atan(.5), math.pi/4, math.atan(2)]
    headings=sorted(a+q*math.pi/2 for q in range(4) for a in headings)
    for heading in headings:
        pose_s=[1.01,1.01,heading]
        for corner in corners(pose_s):
            v=grid_cell(corner,[0,0],H)
            smac.append((H*math.dist([50,50],v),pose_s,v))
    # This fixed corner lands in cell (72,66), beyond Rc from center cell (50,50).
    pose=[1.019,1.019,0.0]
    center=grid_cell(pose[:2],[0,0],H)
    vertex=grid_cell(corners(pose)[2],[0,0],H)
    distance=H*math.dist(center,vertex)
    costs={str(r):emitted_cost(distance,r) for r in [.4,RC,.56,.58]}
    safe_bound=RC+math.sqrt(2)*H
    return {'schema':'d0-costfield-coverage.v1', 'classification':'INDEPENDENT_RECONSTRUCTION',
        'native_checker_status':'NATIVE_NOT_RUN', 'ri_m':RI, 'rc_m':RC, 'resolution_m':H,
        'native_formula_threshold':threshold,
        'conditions':{
            'support':'h * ceil(inflation_radius / h) >= D_star',
            'positive_smac_threshold':'C(D_star) >= T > 0; otherwise actual full-footprint path must bypass center shortcut',
            'mppi':'C(D_star) >= 1 AND (C(D_star) >= T OR T < 1); consider_footprint=true; actual layer/readback must match',
            'scope':'D_star is maximum center-cell to lethal raster boundary-cell offset for the checker/footprint/yaw lattice. Formula is a gate precondition, not collision proof.',
            'conservative_vertex_bound':'Rc + sqrt(2)*h bounds floor-quantized vertex offsets. It is not a proof for every implementation of line rasterization, unknown/map edges, layer updates or sampled motion.',
        },
        'smac_snapped_16_bin_vertex_sweep': {'samples':len(smac), 'pose_center_m':[1.01,1.01], 'max_vertex_distance_m':max(x[0] for x in smac), 'expanded_058_radius_below_threshold':sum(emitted_cost(x[0],.58)<threshold for x in smac), 'headings_rad':headings, 'scope':'Snapped cell-center and original primitive 16 cardinal/atan headings; not planner replay or proof of internal bin interpolation'},
        'finite_sweep':{'scope':'Arbitrary MPPI continuous poses, not Smac snapping', 'yaw_samples':64,'subcell_offsets_per_axis':[0,.25,.5,.95], 'vertex_samples':len(rows),
                        'max_vertex_distance_m':worst[0],'worst_pose':worst[1],'center_cell':worst[2],'vertex_cell':worst[3],
                        'old_radius_misses':sum(emitted_cost(r[0],.4)<threshold for r in rows),
                        'expanded_058_radius_below_threshold':sum(emitted_cost(r[0],.58)<threshold for r in rows),
                        'not_universal_proof':True},
        'vertex_bound_m':safe_bound, 'bound_support_candidate_m':H*math.ceil(safe_bound/H),
        'bound_formula_cost':inflation_cost(safe_bound),
        'smac_snapped_corner_counterexample': {'pose':[1.01,1.01,0], 'center_cell':[50,50], 'single_lethal_cell':grid_cell(corners([1.01,1.01,0])[2],[0,0],H), 'note':'Check actual installed mapping separately; no native invocation'},
        'counterexample':{'id':'quantized_corner_center_skip','pose':pose, 'padded_size_m':PADDED,
                         'grid':{'resolution':H,'origin':[0,0],'width':100,'height':100},
                         'center_cell':center,'single_lethal_cell':vertex,'raw_lethal_cost':254,
                         'center_source_distance_m':distance,'center_raw_cost_by_inflation_radius':costs,
                         'threshold':threshold,'expanded_058_source_gate':gate(costs['0.58'],threshold),
                         'expected_full_footprint_collision':True,
                         'expected_source_reconstructed_smac_full_check_eligible':False,
                         'expected_source_reconstructed_mppi_full_check_eligible':False,
                         'expected_native_checker_result':None,
                         'note':'Place a lethal cell at the floor-quantized padded corner. Construct the synthetic raw field by max emitted_cost over that source; not by reverse-mapping OccupancyGrid. Exact installed native result remains to be tested.'},
        'decision':'Increasing support alone is not a universal discrete gate fix. Use collision eligibility plus exact oriented footprint, retaining narrow-corridor pass. Do not turn circumcircle/inflation into lethal geometry.'}

if __name__=='__main__':
    out=Path(__file__).parent/'results'/'coverage.json'
    out.write_text(json.dumps(evaluate(),indent=2)+'\n')
    print(out)
