"""Journal archive: one day of existing records, read and never written.

Journal became a reader of nightly reflections; this adds the other half of the
archive, the day itself, from records that already exist:

  scenes      companion-life/episodes/<date>.jsonl (imagined_episode rows)
  photos      image-timeline captures, joined to a scene ONLY through the scene id
              the capture recorded when it was taken (capture.scene.id)
  plan        companion-life/plans/<date>.json (a plan, not a record of what happened)
  reflection  the nightly Lifelog entries content.journals() already reads
  you two     relationship moments whose explicit `happened_on` is this date

Every one of those is authored by the companion or its routines. Nothing here is
evidence that the owner took part, and nothing here is inferred to fill a gap: a
photo that merely shares the calendar date is not attached to a scene, and a day
with no shared moment on record simply has no "you two" section.

Reading is all this does. It calls no model, schedules nothing and writes no file,
so opening, switching or refreshing the archive changes nothing on disk.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

DAY = re.compile(r'\d{4}-\d{2}-\d{2}')


def _zone(c):
    try:return ZoneInfo(c.timezone or 'UTC')
    except Exception:return dt.timezone.utc


def parse_day(value):
    """A calendar date, kept a date. Anything else is refused, not guessed at."""
    if not isinstance(value,str) or not DAY.fullmatch(value):raise ValueError('Choose a date as YYYY-MM-DD')
    try:return dt.date.fromisoformat(value)
    except ValueError:raise ValueError('Choose a real calendar date')


def local_moment(value,tz):
    """The instant as a local datetime, or None when there is no honest instant.

    A naive timestamp says nothing about which midnight it belongs to, and a
    date-only string is a date, not midnight; neither is given a time here.
    """
    if not isinstance(value,str) or DAY.fullmatch(value):return None
    try:moment=dt.datetime.fromisoformat(value)
    except ValueError:return None
    if moment.tzinfo is None:return None
    return moment.astimezone(tz)


def local_day(value,tz):
    moment=local_moment(value,tz)
    return moment.date().isoformat() if moment else None


# ---------------------------------------------------------------- scenes
def _episodes(c,day,tz):
    """Rows whose recorded instant falls on `day` in the profile's timezone.

    Files are named by the date the writer saw, so a change of timezone or a row
    written just across midnight can sit in a neighbouring file; those are read
    too and placed by their instant. A row without a usable instant is kept only
    from the file named for this very date, and carries no time.
    """
    import companion_life as life
    rows=[];unavailable=False;found=False
    for offset in (-1,0,1):
        name=(day+dt.timedelta(days=offset)).isoformat()
        path=c.life/'episodes'/f'{name}.jsonl'
        if path.is_symlink():
            if offset==0:unavailable=True
            continue
        try:read=life.read_events(c.life,name,limit=0)
        except OSError:
            if offset==0 or path.exists():unavailable=True
            continue
        except ValueError:continue
        if offset==0:found=path.is_file()
        for row in read:
            if not isinstance(row,dict):continue
            moment=local_moment(row.get('recorded_at'),tz)
            if moment is not None:
                if moment.date()==day:rows.append((moment,row))
            elif offset==0:
                rows.append((None,row))
    # Rows keep file order within an instant; untimed rows go last, unordered claims aside.
    timed=sorted((x for x in rows if x[0] is not None),key=lambda x:x[0].astimezone(dt.timezone.utc))
    return timed+[x for x in rows if x[0] is None],unavailable,found


def _signature(row):
    """What makes two snapshots the same scene for display."""
    state=row.get('state') if isinstance(row.get('state'),dict) else None
    if state is None:return None
    return ({k:v for k,v in state.items() if k!='transition'},row.get('status'))


def _status(row):
    status=row.get('status')
    if status=='planned':return 'planned'
    if status=='skipped':return 'skipped'
    state=row.get('state') if isinstance(row.get('state'),dict) else {}
    if state.get('confirmed') is False:return 'carried_forward'
    return 'recorded'


def _text(value,limit):
    return value.strip()[:limit] if isinstance(value,str) else ''


def scenes(c,day,tz):
    """Adjacent identical snapshots collapse into one scene for display only.

    The presence loop re-records an unchanged present every few minutes; stored
    history keeps every row, and each collapsed scene lists the ids it covers so a
    photo taken during any of them still finds its scene.
    """
    rows,unavailable,found=_episodes(c,day,tz)
    out=[]
    for moment,row in rows:
        sig=_signature(row)
        last=out[-1] if out else None
        if last and sig is not None and last['_sig']==sig and moment is not None and last['_timed']:
            last['ids'].append(str(row.get('id','')))
            last['snapshots']+=1
            last['last_at']=moment.isoformat()
            continue
        state=row.get('state') if isinstance(row.get('state'),dict) else {}
        out.append({'_sig':sig,'_timed':moment is not None,
                    'id':str(row.get('id','')),'ids':[str(row.get('id',''))],
                    'at':moment.isoformat() if moment else None,
                    'last_at':moment.isoformat() if moment else None,
                    'time_known':moment is not None,
                    'status':_status(row),
                    'activity':_text(state.get('activity') or row.get('activity'),120),
                    'mood':_text(state.get('mood'),200),
                    'location':_text(state.get('location'),200),
                    'text':_text(row.get('text'),600),
                    'provenance':_text(row.get('provenance'),300),
                    'snapshots':1,'photos':[],'missing_photos':0})
    for i,scene in enumerate(out):
        nxt=next((x for x in out[i+1:] if x['time_known']),None)
        scene['until']=nxt['at'] if nxt and scene['time_known'] else None
        del scene['_sig'],scene['_timed']
    state='unavailable' if unavailable else ('available' if out else ('empty' if found else 'none'))
    return out,state


# ---------------------------------------------------------------- photos
def attach_photos(c,day,scene_rows,tz):
    """Photos reach a scene only through the scene id their capture recorded.

    Returns (state, unplaced): captures that say they were taken on this day but
    whose scene is not in the day's record are reported apart, under their own
    recorded scene, instead of being pinned to whichever scene was nearby.
    """
    import companion_timeline as timeline
    from .content import catalog
    by_id={}
    for scene in scene_rows:
        for ident in scene['ids']:by_id[ident]=scene
    wanted={};unplaced=[]
    try:records=list(timeline.records(c))
    except (OSError,ValueError):return 'unavailable',[]
    for _,row in records:
        if not isinstance(row,dict) or row.get('status')!='saved':continue
        scene=row.get('scene') if isinstance(row.get('scene'),dict) else {}
        owner=by_id.get(str(scene.get('id',''))) if scene.get('id') else None
        if owner is None:
            if local_day(scene.get('recorded_at'),tz)==day.isoformat():
                state=scene.get('state') if isinstance(scene.get('state'),dict) else {}
                unplaced.append({'capture_id':row.get('id'),'scene_id':scene.get('id'),
                                 'at':local_moment(scene.get('recorded_at'),tz).isoformat(),
                                 'activity':_text(state.get('activity'),120),'photos':[]})
                wanted[row.get('id')]=unplaced[-1]
            continue
        wanted[row.get('id')]=owner
    if not wanted:return 'available',[]
    paths=set()
    for _,row in records:
        if row.get('id') not in wanted:continue
        for name in [row.get('primary_filename'),row.get('filename')]+[v.get('filename') for v in row.get('variants',[]) if isinstance(v,dict)]:
            if isinstance(name,str) and name:paths.add('image-timeline/images/'+name)
    try:found=catalog(c,kind='image',reference_paths=paths)
    except (OSError,ValueError):return 'unavailable',unplaced
    items=found['items']
    # Past the catalog's scan limit an unseen photo may simply not have been reached,
    # so it is not called missing; the day says the photo list is partial instead.
    partial=bool(found.get('scan_limited'))
    seen=set()
    for item in items:
        target=wanted.get(item.get('capture_id'))
        if target is None:continue
        target['photos'].append(item);seen.add(item.get('capture_id'))
    for capture,target in wanted.items():
        if capture not in seen and 'missing_photos' in target and not partial:target['missing_photos']+=1
    for target in {id(x):x for x in wanted.values()}.values():
        target['photos'].sort(key=lambda x:x.get('at',''))
    return 'partial' if partial else 'available',[x for x in unplaced if x['photos']]


# ---------------------------------------------------------------- the rest
def plan(c,day):
    import companion_plan
    path=c.life/companion_plan.FOLDER/f'{day.isoformat()}.json'
    if path.is_symlink():return {'state':'unavailable','items':[]}
    if not path.exists():return {'state':'none','items':[]}
    data=companion_plan.read_for(c.life,day)
    if data is None:return {'state':'unavailable','items':[]}
    items=[{'start':_text(x.get('start'),10),'end':_text(x.get('end'),10),'what':_text(x.get('what'),200),
            'where':_text(x.get('where'),200),'status':_text(x.get('status'),20) or 'planned'}
           for x in data['items']]
    return {'state':'available' if items else 'empty','items':items,'intent':_text(data.get('intent'),400)}


def reflection(c,day):
    from .content import journals
    data=journals(c,limit=1000,q=day.isoformat())
    entries=[{k:e[k] for k in ('id','day','excerpt','words','source','truncated')} for e in data['entries'] if e['day']==day.isoformat()]
    # A file that could not be read might have held this day's entry: say so rather
    # than reporting a day with nothing written.
    partial=bool(data['warnings'])
    state='available' if entries else ('unavailable' if partial else 'none')
    return {'state':state,'entries':entries,'warnings':data['warnings']}


def together(c,day):
    """Only moments explicitly recorded as happening on this date."""
    import companion_notes as notes
    path=notes.moments_path(c)
    if path.is_symlink():return {'state':'unavailable','moments':[]}
    try:rows=notes.moments(c,None)
    except (OSError,ValueError,KeyError,TypeError):return {'state':'unavailable','moments':[]}
    rows=[{'id':r.get('id'),'moment':r.get('moment'),'text':_text(r.get('text'),500),'happened_on':r.get('happened_on'),
           'status':r.get('status')} for r in rows if r.get('happened_on')==day.isoformat()]
    return {'state':'available' if rows else 'none','moments':rows}


def archive_day(c,value):
    tz=_zone(c);day=parse_day(value)
    rows,scene_state=scenes(c,day,tz)
    photo_state,unplaced=attach_photos(c,day,rows,tz)
    return {'timezone':c.timezone,'day':day.isoformat(),'today':dt.datetime.now(tz).date().isoformat(),
            'agent':c.agent,'human':c.human,
            'scenes':rows,'unplaced_photos':unplaced,
            'plan':plan(c,day),'reflection':reflection(c,day),'together':together(c,day),
            'sources':{'scenes':scene_state,'photos':photo_state}}


def archive_index(c):
    """Which dates hold anything, for the date picker. Same placement rules as a day."""
    import companion_life as life
    tz=_zone(c);days={}
    folder=c.life/'episodes'
    try:names=sorted(p.stem for p in folder.glob('????-??-??.jsonl') if not p.is_symlink())
    except OSError:names=[]
    unavailable=False
    for name in names[-1500:]:
        try:rows=life.read_events(c.life,name,limit=0)
        except (OSError,ValueError):unavailable=True;continue
        for row in rows:
            key=local_day(row.get('recorded_at'),tz) if isinstance(row,dict) else None
            if key is None and isinstance(row,dict):key=name
            if key:days.setdefault(key,{'scenes':False,'reflection':False})['scenes']=True
    from .content import journals
    data=journals(c,limit=1000);warnings=data['warnings']
    while True:
        for e in data['entries']:days.setdefault(e['day'],{'scenes':False,'reflection':False})['reflection']=True
        if not data['next_cursor']:break
        data=journals(c,limit=1000,before=data['next_cursor'])
    return {'timezone':c.timezone,'today':dt.datetime.now(tz).date().isoformat(),
            'days':dict(sorted(days.items())),'scenes_unavailable':unavailable,'warnings':warnings}


def register(app,load):
    @app.get('/api/journal/archive')
    def journal_archive_index():return archive_index(load())
    @app.get('/api/journal/archive/{day}')
    def journal_archive_day(day:str):return archive_day(load(),day)
