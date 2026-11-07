"""Regression coverage for interviews losing people after a static crop."""
from __future__ import annotations

import tempfile
from pathlib import Path
import subprocess
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from app.framing import (Box, assess, apply_frame, crop_for, plan_from_observations,
                         retention, render_base, FaceDetector, attach_quality, analyze)


class FramingPlanTests(unittest.TestCase):
    def test_invalid_intervals_are_rejected_before_decoding(self):
        for start,end in [(-1,2),(0,0),(0,float('nan')),(float('inf'),4)]:
            with self.assertRaises(ValueError): analyze(Path('unused.mp4'),start,end)

    def test_unknown_samples_cannot_hide_a_continuous_visibility_gap(self):
        face=Box(.4,.2,.1,.2)
        plan=plan_from_observations(1600,900,20,[(i/4,[] if i in (21,23) else [face],False) for i in range(80)])
        output=[[] if 20<=i<=24 else plan.projected_faces(s.t) for i,s in enumerate(plan.samples)]
        result=assess(plan,output)
        self.assertGreaterEqual(result['retention_rate'],.95)
        self.assertEqual(result['max_unverified_output_seconds'],1.25)
        self.assertEqual(result['status'],'needs_review')
    def test_off_center_shots_preserve_faces_without_panning_through_cut(self):
        observations=[]
        for i in range(48):
            t=i/4; center=.5 if t<4 else .13 if t<8 else .87
            observations.append((t,[Box(center-.04,.2,.08,.16)],t in (4,8)))
        plan=plan_from_observations(1600,900,12,observations)
        for s in plan.samples:
            self.assertGreaterEqual(retention(s.targets[0],s.crops[0]),.99)
        self.assertEqual(plan.crops_at(3.99),plan.samples[15].crops)
        self.assertLess(plan.crops_at(4)[0].x,.1)
        self.assertGreater(plan.crops_at(8)[0].x,.6)
        # Perfect output evidence must pass for all three camera positions.
        result=assess(plan,[plan.projected_faces(s.t) for s in plan.samples])
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['max_lost_face_seconds'],0)

    def test_two_separated_faces_get_distinct_stacked_panels(self):
        faces=[Box(.13,.2,.09,.18),Box(.75,.2,.09,.18)]
        plan=plan_from_observations(1600,900,1,[(i/4,faces,False) for i in range(4)])
        self.assertEqual(plan.samples[0].layout,'stacked')
        self.assertEqual(len(plan.samples[0].crops),2)
        self.assertLess(plan.projected_faces(0)[0].cy,.5)
        self.assertGreater(plan.projected_faces(0)[1].cy,.5)
        for f,c in zip(faces,plan.samples[0].crops):
            self.assertGreaterEqual(retention(f,c),.99)

    def test_unknown_source_is_reviewed_not_approved(self):
        plan=plan_from_observations(1600,900,2,[(i/4,[],False) for i in range(8)])
        result=assess(plan,[[]]*8)
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(result['source_face_frames'],0)

    def test_output_losing_face_fails_even_if_plan_geometry_is_valid(self):
        face=Box(.45,.2,.1,.2)
        plan=plan_from_observations(1600,900,2,[(i/4,[face],False) for i in range(8)])
        result=assess(plan,[[]]*8)
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(result['max_lost_face_seconds'],2)

    def test_brief_miss_holds_track_but_cut_resets_it(self):
        face=Box(.1,.2,.1,.2)
        plan=plan_from_observations(1600,900,1,[(0,[face],False),(.25,[],False),
            (.5,[],True),(.75,[Box(.8,.2,.1,.2)],False)])
        self.assertTrue(plan.samples[1].held)
        self.assertEqual(plan.samples[2].layout,'unverified')
        self.assertFalse(plan.samples[2].targets)

    def test_smoothing_never_discards_face_during_motion(self):
        observations=[(i/4,[Box(.12+i*.018,.2,.09,.18)],False) for i in range(20)]
        plan=plan_from_observations(1600,900,5,observations)
        for s in plan.samples:
            self.assertGreaterEqual(retention(s.targets[0],s.crops[0]),.99)

    def test_caption_band_avoids_projected_face(self):
        plan=plan_from_observations(720,1280,1,[(i/4,[Box(.2,.58,.5,.2)],False) for i in range(4)])
        y=plan.caption_y(0)
        self.assertLess(sum(retention(f,Box(.07,y-.15,.86,.16)) for f in plan.projected_faces(0)),.01)

    def test_landscape_and_portrait_crops_have_requested_aspect(self):
        for w,h in [(1600,900),(720,1280),(500,1200)]:
            for aspect in [9/16,9/8]:
                crop=crop_for(Box(.65,.2,.1,.15),w,h,aspect)
                self.assertAlmostEqual(crop.w*w/(crop.h*h),aspect)

    def test_actual_pixels_follow_the_subject_in_all_three_shots(self):
        for center in [.5,.13,.87]:
            img=np.zeros((900,1600,3),np.uint8)
            face=Box(center-.04,.2,.08,.16)
            x,y,w,h=[round(v*s) for v,s in zip((face.x,face.y,face.w,face.h),(1600,900,1600,900))]
            img[y:y+h,x:x+w]=[0,255,0]
            plan=plan_from_observations(1600,900,1,[(i/4,[face],False) for i in range(4)])
            output=apply_frame(img,plan.crops_at(0),720,1280)
            self.assertGreater(np.count_nonzero(output[:,:,1]>200),10000)

    def test_review_output_has_preview_but_no_ready_url(self):
        plan=plan_from_observations(1600,900,2,[(i/4,[],False) for i in range(8)])
        quality=assess(plan,[[]]*8)
        with tempfile.TemporaryDirectory() as tmp, patch('app.framing.validate_output',return_value=quality):
            out=Path(tmp)/'clip.mp4'; out.touch()
            c=SimpleNamespace()
            attach_quality(c,plan,out,'https://example.test/clip.mp4')
            self.assertEqual(c.framing.status,'needs_review')
            self.assertIsNone(c.render_url)
            self.assertEqual(c.render_preview_url,'https://example.test/clip.mp4')


class ModelTests(unittest.TestCase):
    def test_bundled_detector_loads_without_network(self):
        detector=FaceDetector()
        self.assertEqual(detector(np.zeros((320,320,3),np.uint8)),[])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class AudioAlignmentTests(unittest.TestCase):
    def test_smart_render_uses_audio_from_selected_interval(self):
        from app.contracts import Clip,ClipSet,Transcript
        from app.pipeline import s6_render_adaptive as renderer
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); src=root/'source.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
                '-f','lavfi','-i','testsrc2=size=320x180:rate=30',
                '-f','lavfi','-i','sine=frequency=440:duration=2',
                '-f','lavfi','-i','sine=frequency=880:duration=2',
                '-filter_complex','[1:a][2:a]concat=n=2:v=0:a=1[a]',
                '-map','0:v','-map','[a]','-t','4','-c:v','libx264','-c:a','aac',str(src)],check=True)
            c=Clip(start=2,end=3,score=0,title='audio test',hook_rewrite='',on_screen_lines=[],
                   caption='',matched_pattern='test',reason='verify source offset')
            t=Transcript(source_url='test',video_path=str(src),duration=4,segments=[])
            with patch.object(renderer,'RENDER_DIR',root),patch.object(renderer,'use_fixture',return_value=False):
                result=renderer.run('audio-offset',t,ClipSet(clips=[c]))
            pcm=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-i',result.clips[0].render_path,
                                         '-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'])
            audio=np.frombuffer(pcm,np.float32)
            spectrum=np.abs(np.fft.rfft(audio))
            peak=np.fft.rfftfreq(len(audio),1/8000)[np.argmax(spectrum)]
            self.assertAlmostEqual(peak,880,delta=5)


if __name__=='__main__': unittest.main()
