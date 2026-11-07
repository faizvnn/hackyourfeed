"""Compare static and smart framing using the same local footage and subtitles.

Run from backend: python scripts/evaluate_framing.py --source video.mp4 --end 15
Optional --transcript uses a stage-1 Transcript JSON on the original source timeline.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app import framing
from app.config import RENDER_DIR
from app.contracts import CaptionStyle, Clip, ClipSet, Transcript
from app.pipeline.s6_render_adaptive import RenderOptions, probe, run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--transcript',type=Path)
    p.add_argument('--start',type=float,default=0)
    p.add_argument('--end',type=float,required=True)
    p.add_argument('--job-id',default='framing-evaluation')
    args=p.parse_args()
    if args.end<=args.start: p.error('end must exceed start')
    options=RenderOptions.from_env()
    t=(Transcript.model_validate_json(args.transcript.read_text(encoding='utf-8')) if args.transcript
       else Transcript(source_url='local://framing-evaluation',segments=[]))
    t.video_path=str(args.source.resolve())
    t.duration=probe(args.source,options)['duration']
    def selected():
        return ClipSet(clips=[Clip(start=args.start,end=args.end,score=0,title='Framing evaluation',
            hook_rewrite='',on_screen_lines=[],caption='Technical framing evaluation',
            matched_pattern='evaluation',reason='Same source, same interval, different framing',
            render_style=CaptionStyle(hook_seconds=0))])
    baseline=run(args.job_id+'-before',t,selected(),options=replace(options,framing='static',layout='crop'))
    improved=run(args.job_id+'-after',t,selected(),options=replace(options,framing='smart',layout='crop'))
    plan=framing.analyze(args.source,args.start,args.end)
    center=options.crop_center_x
    cw=min(1,plan.height*9/16/plan.width); ch=min(1,plan.width*16/9/plan.height)
    crop=framing.Box(max(0,min(1-cw,center-cw/2)),(1-ch)/2,cw,ch)
    static_plan=replace(plan,samples=[replace(s,crops=[crop],targets=s.faces[:1],layout='single')
                                     for s in plan.samples])
    before=Path(baseline.clips[0].render_path); after=Path(improved.clips[0].render_path)
    report=dict(source=str(args.source.resolve()),start=args.start,end=args.end,
        before=framing.validate_output(static_plan,before),after=improved.clips[0].framing.model_dump(),
        files=dict(before=str(before),after=str(after)),
        limitation='Sampled face detection measures framing, not active-speaker identity or all-frame quality.')
    out=RENDER_DIR/(args.job_id+'-after')/'comparison.json'
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    contact_sheet(args.source,args.start,args.end,before,after,out.with_suffix('.jpg'))
    print(json.dumps(report,indent=2))


def contact_sheet(source,start,end,before,after,out):
    import cv2
    from PIL import Image, ImageDraw, ImageFont
    canvas=Image.new('RGB',(1080,1020),'#111821'); draw=ImageDraw.Draw(canvas)
    font=ImageFont.load_default(size=19)
    def image_at(path,t):
        cap=cv2.VideoCapture(str(path)); cap.set(cv2.CAP_PROP_POS_MSEC,t*1000)
        ok,img=cap.read(); cap.release()
        if not ok: raise RuntimeError(f'Cannot read evaluation frame {path} at {t}')
        return Image.fromarray(cv2.cvtColor(img,cv2.COLOR_BGR2RGB))
    duration=end-start
    for row,fraction in enumerate((1/6,.5,5/6)):
        t=duration*fraction
        for path,offset,x,width,label in [(source,start,12,560,'Source'),(before,0,600,170,'Before'),(after,0,810,170,'Smart framing')]:
            img=image_at(path,offset+t); img.thumbnail((width,285))
            draw.text((x,row*340+10),f'{label} / {t:.1f}s',font=font,fill='white')
            canvas.paste(img,(x,row*340+45))
    canvas.save(out,quality=92)


if __name__=='__main__': main()
