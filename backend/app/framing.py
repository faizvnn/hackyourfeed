"""Shot-aware, face-guided framing shared by both renderers.

Coordinates are normalized source-frame coordinates; all times are clip-relative.
Detection is evidence of a face, never a claim about who is speaking. Ambiguous
shots remain reviewable. No model download or cloud service is used at runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np

MODEL = Path(__file__).parent / "assets" / "face_detection_yunet_2023mar.onnx"
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SAMPLE_FPS = 4


def _cv():
    try:
        import cv2
        return cv2
    except ImportError as exc:
        raise RuntimeError("Smart framing requires opencv-python-headless; install requirements-render.txt") from exc


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self): return self.x + self.w / 2

    @property
    def cy(self): return self.y + self.h / 2


def retention(face: Box, crop: Box) -> float:
    intersection = max(0, min(face.x + face.w, crop.x + crop.w) - max(face.x, crop.x))
    intersection *= max(0, min(face.y + face.h, crop.y + crop.h) - max(face.y, crop.y))
    return intersection / max(1e-9, face.w * face.h)


class FaceDetector:
    def __init__(self):
        cv = _cv()
        if not MODEL.is_file() or hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
            raise RuntimeError("Bundled YuNet model is missing or corrupt; restore app/assets from the repository")
        self.net = cv.FaceDetectorYN_create(str(MODEL), "", (320, 320), .85, .3, 5000)

    def __call__(self, image) -> list[Box]:
        cv = _cv()
        h, w = image.shape[:2]
        ratio = min(1, 960 / w)
        small = cv.resize(image, None, fx=ratio, fy=ratio) if ratio < 1 else image
        self.net.setInputSize((small.shape[1], small.shape[0]))
        _, rows = self.net.detect(small)
        result = []
        for row in ([] if rows is None else rows):
            x, y, fw, fh = [float(v) for v in row[:4]]
            x, y, fw, fh = x / small.shape[1], y / small.shape[0], fw / small.shape[1], fh / small.shape[0]
            left, top = max(0, x), max(0, y)
            right, bottom = min(1, x + fw), min(1, y + fh)
            if right > left and bottom > top:
                result.append(Box(left, top, right-left, bottom-top))
        return sorted(result, key=lambda b: b.w*b.h, reverse=True)


@dataclass
class Sample:
    t: float
    shot: int
    faces: list[Box]
    crops: list[Box]
    targets: list[Box]
    layout: str  # single, stacked, unverified
    held: bool = False


@dataclass
class FramingPlan:
    width: int
    height: int
    duration: float
    samples: list[Sample]
    sample_fps: float = SAMPLE_FPS
    warnings: list[str] = field(default_factory=list)

    def at(self, t: float) -> Sample:
        # O(1) for the fixed-rate analysis grid, including short final intervals.
        return self.samples[min(len(self.samples)-1, max(0, int(t * self.sample_fps + 1e-6)))]

    def crops_at(self, t: float) -> list[Box]:
        i = min(len(self.samples)-1, max(0, int(t * self.sample_fps + 1e-6)))
        a = self.samples[i]
        if i+1 == len(self.samples): return a.crops
        b = self.samples[i+1]
        # Never interpolate across a camera cut or layout change.
        if a.shot != b.shot or a.layout != b.layout or len(a.crops) != len(b.crops): return a.crops
        k = max(0, min(1, (t-a.t) / max(1e-6, b.t-a.t)))
        return [Box(*(getattr(x, key)*(1-k)+getattr(y, key)*k for key in ("x","y","w","h")))
                for x,y in zip(a.crops,b.crops)]

    def projected_faces(self, t: float) -> list[Box]:
        s = self.at(t)
        crops = self.crops_at(t)
        n = len(crops)
        return [Box((f.x-c.x)/c.w, ((f.y-c.y)/c.h+i)/n, f.w/c.w, f.h/c.h/n)
                for i,(f,c) in enumerate(zip(s.targets,crops))]

    def caption_y(self, t: float) -> float:
        faces = self.projected_faces(t)
        # Bounding bands include two lines and an outline, above player controls.
        candidates = (.78, .88, .64, .52)
        return min(candidates, key=lambda y: sum(retention(f,Box(.07,y-.15,.86,.16)) for f in faces))

    def save(self, path: Path):
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def crop_for(face: Box, width: int, height: int, aspect: float, previous: Box | None = None) -> Box:
    cw = min(1., height * aspect / width)
    ch = min(1., width / aspect / height)
    if aspect > 1:  # A tighter upper-body crop for each stacked participant.
        ch = min(ch, max(.35, face.h*3.5, face.w*width/height/aspect*1.5))
        cw = ch*height*aspect/width
    x = max(0., min(1-cw, face.cx-cw/2))
    y = max(0., min(1-ch, face.cy-ch*.36))
    if previous is not None:
        x = previous.x*.35+x*.65
        y = previous.y*.35+y*.65
        # Smoothing must not lag so far behind that it crops the face away.
        if face.w <= cw:
            x = max(face.x+face.w-cw, min(x, face.x))
        if face.h <= ch:
            y = max(face.y+face.h-ch, min(y, face.y))
    return Box(max(0,min(1-cw,x)),max(0,min(1-ch,y)),cw,ch)


def plan_from_observations(width: int, height: int, duration: float,
                           observations: list[tuple[float,list[Box],bool]], sample_fps=SAMPLE_FPS) -> FramingPlan:
    samples, shot = [], 0
    previous_faces, previous_crops = [], []
    last_seen = -100.
    for t,faces,cut in observations:
        # A large face-position jump also handles hard cuts against similar backgrounds.
        jump = bool(faces and previous_faces and len(faces)==len(previous_faces)==1
                    and abs(faces[0].cx-previous_faces[0].cx) > .25)
        if cut or jump:
            shot += 1; previous_faces, previous_crops = [], []; last_seen = -100.
        held = False
        detected = list(faces)
        if faces:
            last_seen = t
        elif previous_faces and t-last_seen <= .5 and not cut:
            faces, held = previous_faces, True
        if not faces:
            # Inspectable fallback, never treated as a verified interview.
            fallback = crop_for(Box(.5,.5,0,0),width,height,9/16)
            crops, targets, layout = [fallback], [], "unverified"
        else:
            largest = sorted(faces,key=lambda b:b.w*b.h,reverse=True)
            pair = (len(largest)>=2 and largest[1].w*largest[1].h >= largest[0].w*largest[0].h*.4
                    and abs(largest[0].cx-largest[1].cx) > .2)
            targets = sorted(largest[:2],key=lambda b:b.cx) if pair else largest[:1]
            layout = "stacked" if pair else "single"
            aspect = 9/8 if pair else 9/16
            old = previous_crops if samples and samples[-1].layout==layout else []
            crops = [crop_for(f,width,height,aspect,old[i] if i<len(old) else None) for i,f in enumerate(targets)]
        samples.append(Sample(t,shot,detected,crops,targets,layout,held))
        previous_faces, previous_crops = list(faces), crops
    if not samples:
        raise ValueError("No video frames available for framing analysis")
    warnings = ["Face detection cannot determine which person is speaking."]
    return FramingPlan(width,height,duration,samples,sample_fps,warnings)


def analyze(src: Path, start: float, end: float, detector=None) -> FramingPlan:
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError("Framing requires a finite, positive source interval")
    cv = _cv()
    detector = detector or FaceDetector()
    cap = cv.VideoCapture(str(src))
    if not cap.isOpened(): raise RuntimeError("Cannot open source for framing analysis")
    fps = cap.get(cv.CAP_PROP_FPS)
    if not math.isfinite(fps) or fps <= 0:
        cap.release(); raise RuntimeError("Cannot determine source frame rate")
    source_duration = cap.get(cv.CAP_PROP_FRAME_COUNT) / fps
    if source_duration > 0 and end > source_duration + .05:
        cap.release(); raise ValueError("Framing interval exceeds the actual source duration")
    cap.set(cv.CAP_PROP_POS_MSEC,start*1000)
    observations, prev_gray, index, next_sample = [], None, 0, 0.
    duration = end-start
    try:
        while index/fps < duration:
            ok, image = cap.read()
            if not ok: break
            t = index/fps; index += 1
            if t+1e-6 < next_sample: continue
            h,w = image.shape[:2]
            gray = cv.cvtColor(cv.resize(image,(96,54)),cv.COLOR_BGR2GRAY)
            cut = prev_gray is not None and float(np.mean(cv.absdiff(gray,prev_gray)))/255 > .18
            faces = detector(image)
            observations.append((next_sample,faces,cut))
            prev_gray=gray; next_sample += 1/SAMPLE_FPS
    finally:
        cap.release()
    if not observations:
        raise RuntimeError("No source frames available in the requested interval")
    return plan_from_observations(w,h,duration,observations)


def apply_frame(image, crops: list[Box], width: int, height: int):
    cv = _cv(); h,w = image.shape[:2]
    panels=[]
    for i,c in enumerate(crops):
        x,y = max(0,round(c.x*w)),max(0,round(c.y*h))
        right,bottom = min(w,round((c.x+c.w)*w)),min(h,round((c.y+c.h)*h))
        if right<=x or bottom<=y: raise RuntimeError("Empty crop generated")
        panel_height = height//len(crops) if i<len(crops)-1 else height-height//len(crops)*i
        panels.append(cv.resize(image[y:bottom,x:right],(width,panel_height),interpolation=cv.INTER_AREA))
    return np.ascontiguousarray(np.vstack(panels))


def render_base(src: Path, start: float, out: Path, plan: FramingPlan, width: int, height: int,
                fps: int, ffmpeg="ffmpeg", timeout=300):
    """Uniform FFmpeg decode keeps frame timing and rotation aligned with the final audio."""
    decoder=encoder=None
    deadline=time.monotonic()+timeout
    with tempfile.TemporaryFile() as dec_log, tempfile.TemporaryFile() as enc_log:
        try:
            decoder=subprocess.Popen([ffmpeg,"-hide_banner","-loglevel","error","-nostdin",
                "-ss",str(start),"-i",str(src),"-t",str(plan.duration),"-an",
                "-vf",f"fps={fps},scale={plan.width}:{plan.height}","-pix_fmt","bgr24",
                "-f","rawvideo","pipe:1"],stdout=subprocess.PIPE,stderr=dec_log)
            encoder=subprocess.Popen([ffmpeg,"-hide_banner","-loglevel","error","-y",
                "-f","rawvideo","-pix_fmt","bgr24","-s",f"{width}x{height}","-r",str(fps),
                "-i","pipe:0","-an","-c:v","libx264","-preset","veryfast","-crf","18",
                "-pix_fmt","yuv420p",str(out)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=enc_log)
            size=plan.width*plan.height*3; count=0
            while True:
                if time.monotonic()>deadline: raise TimeoutError("Smart framing exceeded its time budget")
                data=decoder.stdout.read(size)
                if not data: break
                if len(data)!=size: raise RuntimeError("Truncated raw frame from FFmpeg")
                img=np.frombuffer(data,np.uint8).reshape(plan.height,plan.width,3)
                framed=apply_frame(img,plan.crops_at(count/fps),width,height)
                encoder.stdin.write(framed.tobytes()); count+=1
            encoder.stdin.close(); decoder.stdout.close()
            decoder.wait(timeout=max(1,deadline-time.monotonic()))
            encoder.wait(timeout=max(1,deadline-time.monotonic()))
            if decoder.returncode or encoder.returncode or count==0:
                raise RuntimeError("Smart framing FFmpeg failed")
        except (OSError,subprocess.SubprocessError,TimeoutError,RuntimeError) as exc:
            for process in (decoder,encoder):
                if process and process.poll() is None: process.kill(); process.wait()
            enc_log.seek(0); dec_log.seek(0)
            detail=(dec_log.read()+enc_log.read()).decode("utf-8",errors="replace")[-1000:]
            raise RuntimeError(f"{exc}: {detail}") from exc


def _overlap(a: Box,b: Box):
    # Intersection over the smaller box tolerates moderate detector scale differences.
    x=max(0,min(a.x+a.w,b.x+b.w)-max(a.x,b.x)); y=max(0,min(a.y+a.h,b.y+b.h)-max(a.y,b.y))
    return x*y/max(1e-9,min(a.w*a.h,b.w*b.h))


def assess(plan: FramingPlan, output_faces: list[list[Box]]) -> dict:
    eligible=retained=0; bad_run=unknown_run=max_bad=max_unknown=unsafe_run=max_unsafe=0.
    for i,s in enumerate(plan.samples):
        dt=min(1/plan.sample_fps,plan.duration-s.t)
        if not s.faces:
            unknown_run+=dt; max_unknown=max(max_unknown,unknown_run)
            unsafe_run+=dt; max_unsafe=max(max_unsafe,unsafe_run)
            bad_run=0.; continue
        unknown_run=0.; eligible+=1
        expected=plan.projected_faces(s.t)
        geometric=bool(s.targets) and all(retention(f,c)>=.8 for f,c in zip(s.targets,s.crops))
        detected=i<len(output_faces) and all(any(_overlap(e,f)>=.25 for f in output_faces[i]) for e in expected)
        if geometric and detected:
            retained+=1; bad_run=0.; unsafe_run=0.
        else:
            bad_run+=dt; max_bad=max(max_bad,bad_run)
            unsafe_run+=dt; max_unsafe=max(max_unsafe,unsafe_run)
    rate=retained/eligible if eligible else 0.
    warnings=[]
    if not eligible: warnings.append("No source faces were detected; inspect source content and framing.")
    if max_unknown>1: warnings.append("Source face detection was unavailable for more than one second.")
    if max_bad>1: warnings.append("A source face could not be verified in the output for more than one second.")
    if eligible and rate<.95: warnings.append("Fewer than 95% of eligible face samples passed framing checks.")
    if max_unsafe>1 and max_bad<=1 and max_unknown<=1:
        warnings.append("Output visibility could not be verified continuously for more than one second.")
    status="passed" if eligible and rate>=.95 and max_unsafe<=1 else "needs_review"
    return dict(status=status,sampled_frames=len(plan.samples),source_face_frames=eligible,
                retained_face_frames=retained,retention_rate=round(rate,4),
                max_lost_face_seconds=round(max_bad,3),max_unverified_seconds=round(max_unknown,3),
                max_unverified_output_seconds=round(max_unsafe,3),
                warnings=warnings,method="YuNet sampled at 4 fps; heuristic, not a guarantee of active-speaker visibility")


def validate_output(plan: FramingPlan, path: Path, detector=None) -> dict:
    cv=_cv(); detector=detector or FaceDetector(); cap=cv.VideoCapture(str(path)); faces=[]
    try:
        for sample in plan.samples:
            cap.set(cv.CAP_PROP_POS_MSEC,sample.t*1000)
            ok,image=cap.read()
            faces.append(detector(image) if ok else [])
    finally: cap.release()
    return assess(plan,faces)


def attach_quality(clip, plan: FramingPlan, path: Path, url: str):
    from .contracts import FramingQuality
    quality = validate_output(plan,path)
    path.with_suffix(".quality.json").write_text(json.dumps(quality,indent=2),encoding="utf-8")
    clip.framing = FramingQuality.model_validate(quality)
    clip.render_path = str(path)
    clip.render_url = url if quality["status"] == "passed" else None
    clip.render_preview_url = url if quality["status"] == "needs_review" else None
