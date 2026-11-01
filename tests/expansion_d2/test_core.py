import copy
import json
import hashlib
import tempfile
import unittest
import numpy as np
from robot_dashboard.obstacle_fusion_core import Limits, Tracker, associate, detector_adapter, lift_detections, process_lidar
from experiments.expansion_20261029.d2_perception.scenarios import metadata, scene, rgbd_fixture


class CoreTests(unittest.TestCase):
    def lidar(self, count=1, **kw):
        p,g,_=scene(count,**kw); m=metadata()
        return process_lidar(p,m,ground=g,self_boxes=[{'min':[-.2,-.2,.2],'max':[.2,.2,.4],'meta':m}])

    def test_zero_one_two_low_cone_slope_wall_self(self):
        for n in range(3):
            o=self.lidar(n)
            self.assertEqual(len(o['obstacles']),n+1)
            self.assertGreater(o['dropped_counts']['ground'],500)
            self.assertEqual(o['dropped_counts']['self'],3)
            self.assertTrue(all(x['class_name']=='unknown' for x in o['obstacles']))
            self.assertTrue(all(max(x['geometry']['extent'])>0 for x in o['obstacles']))

    def test_unknown_ground_self_conservative(self):
        p,g,_=scene(0); o=process_lidar(p,metadata())
        self.assertIn('GROUND_UNKNOWN',o['health']['reasons'])
        self.assertEqual(o['dropped_counts']['ground'],0)
        g['uncertainty_m']=.1
        self.assertEqual(process_lidar(p,metadata(),ground=g)['dropped_counts']['ground'],0)

    def test_self_stale_does_not_erase(self):
        p,g,_=scene(0); box={'min':[-100]*3,'max':[100]*3,'meta':metadata(2)}
        o=process_lidar(p,metadata(),ground=g,self_boxes=[box])
        self.assertEqual(o['dropped_counts']['self'],0)

    def test_finite_range_and_bound(self):
        o=process_lidar([[1,0,1],[np.nan,0,0],[100,0,0]],metadata())
        self.assertEqual(o['dropped_counts']['invalid_or_range'],2)
        with self.assertRaisesRegex(ValueError,'BUDGET'): process_lidar(np.zeros((11,3)),metadata(),limits=Limits(max_points=10))

    def test_novelty_never_suppresses(self):
        p,g,_=scene(1,wall=False,body=False)
        for covered,expected in [(False,'UNRESOLVED'),(True,'NEW_TO_REFERENCE')]:
            o=process_lidar(p,metadata(),ground=g,reference={'points':[],'coverage_verified':covered,'localization_uncertainty_m':.01})
            self.assertEqual(o['obstacles'][0]['novelty'],expected)
        o=process_lidar(p,metadata(),ground=g,reference={'points':[[1,0,.3]],'coverage_verified':True,'localization_uncertainty_m':.01})
        self.assertEqual(o['obstacles'][0]['novelty'],'KNOWN')

    def lift(self, mutate=None):
        m=metadata(); d,z,c,model=rgbd_fixture(m)
        if mutate: mutate(d,z,c,model)
        return lift_detections(d,z,m,calibration=c,model_manifest=model)

    def test_rgbd_scale_optical_axis(self):
        o=self.lift()['obstacles'][0]
        self.assertAlmostEqual(o['geometry']['center'][2],1)
        self.assertEqual(o['sensor_support'],'RGBD')
        self.assertEqual(o['provenance']['depth_measurement'],'optical_Z')

    def test_optical_to_local_rotation(self):
        def change(d,z,c,m): c['T_local_depth']=[[0,0,1,0],[-1,0,0,0],[0,-1,0,0],[0,0,0,1]]
        self.assertAlmostEqual(self.lift(change)['obstacles'][0]['geometry']['center'][0],1)

    def test_other_intrinsics_and_distortion(self):
        def change(d,z,c,m):
            c['depth_intrinsics'].update(fx=61.,model='brown_conrady',coeffs=[.01,0,0,0,0])
            c['color_intrinsics'].update(fx=59.,model='brown_conrady',coeffs=[.01,0,0,0,0])
        self.assertEqual(len(self.lift(change)['obstacles']),1)

    def test_invalid_background_only_depth(self):
        for value in (0.,np.nan,3000.):
            self.assertFalse(self.lift(lambda d,z,c,m:z.fill(value))['obstacles'])

    def test_wrong_camera_extrinsics_not_same_pixel(self):
        def change(d,z,c,m): c['T_color_depth'][0][3]=10.
        self.assertFalse(self.lift(change)['obstacles'])
        def invalid(d,z,c,m): c['T_color_depth'][0][0]=2.
        with self.assertRaises(ValueError): self.lift(invalid)

    def test_unverified_calibration_stale_clock_and_class(self):
        for mutate in (lambda d,z,c,m:c.update(verified=False),lambda d,z,c,m:c['meta'].update(stamp_ns='2'),lambda d,z,c,m:m.update(class_names={'0':'crosswalk'})):
            self.assertFalse(self.lift(mutate)['obstacles'])
        d,z,c,model=rgbd_fixture(metadata())
        self.assertFalse(lift_detections(d,z,metadata())['obstacles'])

    def test_fusion_lidar_only_depth_only_and_unique_union(self):
        depth=self.lift(); p=[[0,0,1],[.03,.03,1.02]]
        lidar=process_lidar(p,metadata())
        fused=associate(lidar,depth)
        self.assertEqual(fused['obstacles'][0]['sensor_support'],'FUSED')
        self.assertEqual(len(associate(process_lidar(np.empty((0,3)),metadata()),depth)['obstacles']),1)
        self.assertEqual(len(associate(lidar,{'meta':metadata(),'obstacles':[]})['obstacles']),1)

    def test_ambiguous_close_two_objects_separate(self):
        lidar=process_lidar([[-.12,0,1],[.12,0,1]],metadata())
        out=associate(lidar,self.lift())
        self.assertEqual(len(out['obstacles']),3)
        self.assertIn('AMBIGUOUS_ASSOCIATION',out['health']['reasons'])

    def test_unknown_clock_and_delayed_fusion(self):
        for m in (metadata(5_000_000_000),{**metadata(),'clock_domain':'other'}):
            depth=self.lift(); depth['meta']=m
            out=associate(process_lidar([[0,0,1]],metadata()),depth)
            self.assertEqual(out['obstacles'][0]['sensor_support'],'LIDAR')

    def test_tracking_movement_occlusion_expiry_no_free(self):
        t=Tracker(); a=t.step(process_lidar([[1,0,1]],metadata()))
        key=a['obstacle_frame']['obstacles'][0]['track_id']
        b=t.step(process_lidar([[1.1,0,1]],metadata(1_100_000_000,2)))
        self.assertEqual(key,b['obstacle_frame']['obstacles'][0]['track_id'])
        c=t.step(process_lidar(np.empty((0,3)),metadata(1_200_000_000,3)))
        self.assertEqual(c['obstacle_frame']['obstacles'][0]['state'],'OCCLUDED')
        d=t.step(process_lidar(np.empty((0,3)),metadata(3_000_000_000,4)))
        self.assertEqual(d['obstacle_frame']['obstacles'],[]); self.assertEqual(d['clearing_evidence'],[])

    def test_epoch_map_jump_and_reorder(self):
        t=Tracker(); a=t.step(self.lidar())['obstacle_frame']['obstacles'][0]['track_id']
        with self.assertRaisesRegex(ValueError,'REORDERED'): t.step(self.lidar())
        o=self.lidar(); o['meta']=metadata(2_000_000_000,2,'new-epoch')
        b=t.step(o)['obstacle_frame']['obstacles'][0]['track_id']; self.assertNotEqual(a,b)
        o=self.lidar(); o['meta']=metadata(3_000_000_000,3,'new-epoch'); o['meta']['map_binding']['generation']=1
        self.assertNotEqual(b,t.step(o)['obstacle_frame']['obstacles'][0]['track_id'])

    def test_crossing_ambiguity_new_identity(self):
        t=Tracker(); a=t.step(process_lidar([[-.15,0,1],[.15,0,1]],metadata()))
        b=t.step(process_lidar([[-.05,0,1],[.05,0,1]],metadata(1_100_000_000,2)))
        old={x['track_id'] for x in a['obstacle_frame']['obstacles']}
        new={x['track_id'] for x in b['obstacle_frame']['obstacles'] if x['state']=='OBSERVED'}
        self.assertFalse(old & new)

    def test_fresh_separate_rays_only(self):
        ray={'meta':metadata(),'origin':[0,0,0],'free_endpoint':[1,0,0]}
        bad=copy.deepcopy(ray); bad['meta']['clock_domain']='other'
        o=Tracker().step(self.lidar(),clearing_rays=[ray,bad])
        self.assertEqual(len(o['clearing_evidence']),1)
        self.assertFalse(o['expiry_policy']['expiration_is_free'])

    def test_retired_generation_and_stale_source(self):
        t=Tracker(); t.step(self.lidar())
        o=self.lidar(); o['meta']=metadata(2_000_000_000,2,'new')
        t.step(o)
        with self.assertRaisesRegex(ValueError,'RETIRED'): t.step(self.lidar())
        o['meta']=metadata(3_000_000_000,3,'new'); o['meta']['source_age_ns']=999_000_000
        with self.assertRaisesRegex(ValueError,'STALE_SOURCE'): t.step(o)

    def test_ground_stale_and_unknown_fusion_clock(self):
        p,g,_=scene(); g['meta']=metadata(2)
        self.assertEqual(process_lidar(p,metadata(),ground=g)['dropped_counts']['ground'],0)
        lidar=self.lidar(); lidar['meta']['clock_domain']='UNKNOWN'
        d=self.lift(); d['meta']['clock_domain']='UNKNOWN'
        self.assertIn('FUSION_FRAME_CLOCK_OR_TIME_UNKNOWN',associate(lidar,d)['health']['reasons'])

    def test_model_input_adapter_hash_and_no_class_reinterpretation(self):
        d,z,c,m=rgbd_fixture(metadata())
        with tempfile.NamedTemporaryFile() as model:
            model.write(b'synthetic model identity, not executable'); model.flush()
            m['sha256']=hashlib.sha256(b'synthetic model identity, not executable').hexdigest()
            self.assertEqual(detector_adapter(d,manifest=m,model_path=model.name,native_shape=[40,40]),d)
            m['class_names']['0']='crosswalk'
            with self.assertRaisesRegex(ValueError,'MODEL_CLASS'): detector_adapter(d,manifest=m,model_path=model.name,native_shape=[40,40])
            m['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'MODEL_HASH'): detector_adapter(d,manifest=m,model_path=model.name,native_shape=[40,40])

    def test_disconnected_component_budget(self):
        p=np.array([[x*.3,y*.3,1.] for x in range(40) for y in range(40)])
        o=process_lidar(p,metadata())
        self.assertEqual(len(o['obstacles']),64)
        self.assertEqual(o['dropped_counts']['object_budget'],len(p)-64)

    def test_bounded_deterministic_tracks(self):
        def run():
            t=Tracker(Limits(max_objects=4)); outputs=[]
            for i in range(20):
                o=process_lidar([[i,0,1]],metadata(1_000_000_000+i*10_000_000,i+1))
                outputs.append(t.step(o)); self.assertLessEqual(len(t.tracks),4)
            return json.dumps(outputs,sort_keys=True,allow_nan=False)
        self.assertEqual(run(),run())

if __name__=='__main__': unittest.main()
